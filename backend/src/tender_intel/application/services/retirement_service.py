"""Bulk retirement of expired tenders.

Purge the artefact, retain the record. For each selected tender the stored bytes
of every downloaded document are deleted from storage, the document row keeps its
hash, size, name, source URL and extracted text, and the tender is moved to
``ARCHIVED`` so it leaves the working queue.

Nothing is deleted from the database. The tender row, its metadata, its BOQ
items, its reviews and its eligibility result all survive, because they are the
evidence base for measuring the system against what people actually decided, and
because a tender that was pursued and won becomes a past project the eligibility
module scores against later.

Two calls, same selection logic: :meth:`preview` writes nothing and
:meth:`retire` does the work. The preview exists so the operator sees the exact
list before any file is unlinked, and so the count of tenders excluded for an
unknown closing date is visible rather than implied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from tender_intel.domain.entities import AuditLog, TenderDocument
from tender_intel.domain.enums.document_status import DocumentStatus
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.interfaces.providers import FileStorage
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    TenderDocumentRepository,
    TenderRepository,
)
from tender_intel.domain.retirement import (
    IST,
    RetirementCandidate,
    SkipReason,
    default_cutoff,
    skip_reason,
)
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)

#: Hard ceiling on one operation, so a mistyped cutoff cannot unlink the estate
#: in a single call. The preview reports when it truncates.
MAX_BATCH = 200


@dataclass(slots=True)
class RetirementPlan:
    """What a run would do, or did."""

    cutoff: date
    timezone_name: str
    candidates: list[RetirementCandidate] = field(default_factory=list)
    #: Tenders a date filter can never reach because their closing date is unknown.
    unknown_closing_date: int = 0
    #: True when more tenders matched than MAX_BATCH allows in one operation.
    truncated: bool = False

    @property
    def retirable(self) -> list[RetirementCandidate]:
        return [c for c in self.candidates if c.retirable]

    @property
    def skipped(self) -> list[RetirementCandidate]:
        return [c for c in self.candidates if not c.retirable]

    @property
    def documents_to_purge(self) -> int:
        return sum(c.documents_to_purge for c in self.retirable)

    @property
    def bytes_to_reclaim(self) -> int:
        return sum(c.bytes_to_reclaim for c in self.retirable)


@dataclass(slots=True)
class RetirementOutcome:
    """The result of an executed run."""

    plan: RetirementPlan
    tenders_archived: int = 0
    documents_purged: int = 0
    bytes_reclaimed: int = 0
    #: Files storage refused to delete. The row is left untouched so a retry can
    #: pick it up; a document marked purged whose bytes survive would be a lie.
    failures: list[str] = field(default_factory=list)


def _purgeable(document: TenderDocument) -> bool:
    """Does this document still hold bytes worth reclaiming?"""
    return (
        document.file_path is not None
        and not document.is_purged
        and document.status is DocumentStatus.DOWNLOADED
    )


class TenderRetirementService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        documents: TenderDocumentRepository,
        storage: FileStorage,
        audits: AuditLogRepository,
    ) -> None:
        self._tenders = tenders
        self._documents = documents
        self._storage = storage
        self._audits = audits

    async def preview(self, *, cutoff: date | None = None) -> RetirementPlan:
        """Build the selection without touching storage or the database."""
        return await self._plan(cutoff)

    async def retire(
        self,
        *,
        cutoff: date | None = None,
        tender_ids: list[UUID] | None = None,
        actor_id: UUID,
        actor_role: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> RetirementOutcome:
        """Purge documents and archive tenders.

        ``tender_ids`` narrows the run to an explicit subset of the selection, so
        the operator can confirm the preview and then execute exactly what they
        saw. Ids outside the selection are ignored rather than forced through:
        the selection rules are the authority, not the caller's list.
        """
        plan = await self._plan(cutoff)
        chosen = plan.retirable
        if tender_ids is not None:
            wanted = set(tender_ids)
            chosen = [c for c in chosen if c.tender_id in wanted]

        outcome = RetirementOutcome(plan=plan)
        for candidate in chosen:
            purged, reclaimed, failures = await self._purge_documents(candidate.tender_id)
            outcome.documents_purged += purged
            outcome.bytes_reclaimed += reclaimed
            outcome.failures.extend(failures)
            if await self._archive(candidate.tender_id):
                outcome.tenders_archived += 1

        await self._audit(outcome, chosen, actor_id, actor_role, ip, user_agent)
        return outcome

    # --- selection ----------------------------------------------------------

    async def _plan(self, cutoff: date | None) -> RetirementPlan:
        effective = cutoff or default_cutoff()
        plan = RetirementPlan(cutoff=effective, timezone_name=str(IST))
        plan.unknown_closing_date = await self._tenders.count_unknown_closing_date()

        # One over the ceiling, so truncation is detectable rather than silent.
        tenders = await self._tenders.list_closing_before(effective, MAX_BATCH + 1)
        if len(tenders) > MAX_BATCH:
            plan.truncated = True
            tenders = tenders[:MAX_BATCH]

        for tender in tenders:
            documents = await self._documents.list_for_tender(tender.id)
            holding = [d for d in documents if _purgeable(d)]
            plan.candidates.append(
                RetirementCandidate(
                    tender_id=tender.id,
                    tender_number=tender.tender_number,
                    title=tender.title,
                    status=tender.status,
                    closing_date=tender.closing_date,
                    documents_to_purge=len(holding),
                    bytes_to_reclaim=sum(d.file_size or 0 for d in holding),
                    skip=skip_reason(tender, effective),
                )
            )
        return plan

    # --- execution ----------------------------------------------------------

    async def _purge_documents(self, tender_id: UUID) -> tuple[int, int, list[str]]:
        purged = 0
        reclaimed = 0
        failures: list[str] = []
        for document in await self._documents.list_for_tender(tender_id):
            if not _purgeable(document):
                continue
            path = document.file_path
            assert path is not None  # guaranteed by _purgeable
            try:
                await self._storage.delete(path)
            except Exception as exc:  # a stuck file must not stop the batch
                _log.warning(
                    "retirement.purge_failed",
                    document_id=str(document.id),
                    path=path,
                    error=str(exc),
                )
                # Leave the row alone. Marking it purged while the bytes remain
                # would hide the leak from the next run.
                failures.append(f"{document.id}: {exc}")
                continue
            size = document.file_size or 0
            document.mark_purged()
            await self._documents.update(document)
            purged += 1
            reclaimed += size
        return purged, reclaimed, failures

    async def _archive(self, tender_id: UUID) -> bool:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            return False
        if tender.status is TenderStatus.ARCHIVED:
            return False
        tender.transition_to(TenderStatus.ARCHIVED)
        await self._tenders.update(tender)
        return True

    # --- audit --------------------------------------------------------------

    async def _audit(
        self,
        outcome: RetirementOutcome,
        chosen: list[RetirementCandidate],
        actor_id: UUID,
        actor_role: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        """One entry for the whole operation, naming every tender it touched.

        Six months from now the question is which tenders lost their documents on
        a given day, so the entry carries the list, not just the count.
        """
        await self._audits.add(
            AuditLog(
                action="tender.bulk_retire",
                entity_type="Tender",
                entity_id=None,
                actor_id=actor_id,
                ip_address=ip,
                user_agent=user_agent,
                diff={
                    "actor_role": actor_role,
                    "cutoff": outcome.plan.cutoff.isoformat(),
                    "timezone": outcome.plan.timezone_name,
                    "tenders_archived": outcome.tenders_archived,
                    "documents_purged": outcome.documents_purged,
                    "bytes_reclaimed": outcome.bytes_reclaimed,
                    "retained": "tender row, metadata, BOQ items, reviews, eligibility",
                    "unknown_closing_date_excluded": outcome.plan.unknown_closing_date,
                    "skipped": [
                        {"tender_number": c.tender_number, "reason": c.skip.value}
                        for c in outcome.plan.skipped
                        if c.skip is not None
                    ],
                    "tenders": [
                        {
                            "tender_number": c.tender_number,
                            "tender_id": str(c.tender_id),
                            "closing_date": (
                                c.closing_date.isoformat() if c.closing_date else None
                            ),
                            "documents_purged": c.documents_to_purge,
                        }
                        for c in chosen
                    ],
                    "failures": outcome.failures,
                },
            )
        )


__all__ = [
    "MAX_BATCH",
    "RetirementOutcome",
    "RetirementPlan",
    "SkipReason",
    "TenderRetirementService",
]
