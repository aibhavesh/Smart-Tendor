"""Human review & correction use cases (FR-401..FR-406).

Two distinct acts, deliberately kept apart:

* **Correction** — someone fixes an extracted field. Corrections are written
  back as verified (confidence 1.0) so later analysis operates on the corrected
  data. No verdict is recorded and the tender does not move.
* **Verdict** — a manager decides. It may carry corrections, applied first, and
  it advances the tender.

They were once a single endpoint that required a verdict, which meant a
decision had to be recorded before the corrected recommendation could be seen —
a verdict on the audit log resting on evidence that did not yet exist. Splitting
them is what makes "correct, re-analyse, then decide" possible.

Both record a :class:`TenderReview` with before/after snapshots and write an
audit entry with a diff.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from tender_intel.domain.entities import AuditLog, Tender, TenderReview
from tender_intel.domain.entities.metadata import METADATA_FIELDS
from tender_intel.domain.enums.review import ReviewKind, ReviewVerdict
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import DomainValidationError, EntityNotFoundError
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    TenderMetadataRepository,
    TenderRepository,
    TenderReviewRepository,
)
from tender_intel.domain.services.staleness import verdict_is_stale as _is_stale
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.domain.value_objects.unknown import is_known

_DECIMAL_FIELDS = frozenset({"estimated_value", "emd_amount", "tender_fee"})
_DATE_FIELDS = frozenset({"closing_date"})
#: A verdict needs an analysis to decide on.
_REVIEWABLE = frozenset({TenderStatus.ANALYZED, TenderStatus.REVIEWED})
#: A correction only needs extracted metadata to exist, so it is available from
#: PARSED onward — fixing the extraction before analysing is the normal order.
_CORRECTABLE = frozenset({TenderStatus.PARSED, TenderStatus.ANALYZED, TenderStatus.REVIEWED})
_CORRECTION_SOURCE = "review:correction"


class ReviewService:
    def __init__(
        self,
        *,
        reviews: TenderReviewRepository,
        tenders: TenderRepository,
        metadata_repo: TenderMetadataRepository,
        audits: AuditLogRepository,
    ) -> None:
        self._reviews = reviews
        self._tenders = tenders
        self._metadata_repo = metadata_repo
        self._audits = audits

    # ------------------------------------------------------------------ #
    # Corrections (EMPLOYEE)
    # ------------------------------------------------------------------ #
    async def submit_correction(
        self,
        tender_id: UUID,
        *,
        reviewer_id: UUID,
        corrections: dict[str, str],
        comments: str | None = None,
    ) -> TenderReview:
        if not corrections:
            raise DomainValidationError(
                "a correction must change at least one field; "
                "an empty correction record is noise in the review history"
            )
        tender = await self._require_tender(tender_id)
        if tender.status not in _CORRECTABLE:
            raise DomainValidationError(
                "tender must be extracted (PARSED) before its fields can be corrected"
            )

        before, after = await self._apply_corrections(tender_id, corrections)
        review = await self._reviews.add(
            TenderReview(
                tender_id=tender_id,
                reviewer_id=reviewer_id,
                kind=ReviewKind.CORRECTION,
                comments=comments,
                before_snapshot=before,
                after_snapshot=after,
            )
        )
        # No status transition: correcting a field is not deciding on the bid.
        await self._audit(reviewer_id, tender_id, "tender.correction", None, before, after)
        return review

    # ------------------------------------------------------------------ #
    # Verdict (MANAGER / SUPER_ADMIN)
    # ------------------------------------------------------------------ #
    async def submit_verdict(
        self,
        tender_id: UUID,
        *,
        reviewer_id: UUID,
        verdict: ReviewVerdict,
        comments: str | None = None,
        corrections: dict[str, str] | None = None,
    ) -> TenderReview:
        tender = await self._require_tender(tender_id)
        if tender.status not in _REVIEWABLE:
            raise DomainValidationError("tender must be ANALYZED before it can be reviewed")

        before, after = await self._apply_corrections(tender_id, corrections or {})

        review = await self._reviews.add(
            TenderReview(
                tender_id=tender_id,
                reviewer_id=reviewer_id,
                kind=ReviewKind.VERDICT,
                verdict=verdict,
                comments=comments,
                before_snapshot=before,
                after_snapshot=after,
            )
        )

        if tender.status is TenderStatus.ANALYZED:
            tender.transition_to(TenderStatus.REVIEWED)
            await self._tenders.update(tender)

        await self._audit(reviewer_id, tender_id, "tender.review", verdict, before, after)
        return review

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    async def pending(self, page: PageRequest) -> Page[Tender]:
        # Pending = analysed but not yet decided. A *verdict* advances the tender
        # to REVIEWED; a correction deliberately does not, so a corrected tender
        # stays in the queue until somebody actually decides on it.
        return await self._tenders.list(page, status=TenderStatus.ANALYZED)

    async def history(self, tender_id: UUID) -> list[TenderReview]:
        await self._require_tender(tender_id)
        return await self._reviews.list_for_tender(tender_id)

    async def metadata_updated_at(self, tender_id: UUID) -> datetime | None:
        metadata = await self._metadata_repo.get_for_tender(tender_id)
        return metadata.updated_at if metadata is not None else None

    async def verdict_is_stale(self, tender_id: UUID) -> bool:
        """True when the tender's latest verdict predates a metadata correction."""
        return _is_stale(
            await self._reviews.latest_verdict_at(tender_id),
            await self.metadata_updated_at(tender_id),
        )

    # ------------------------------------------------------------------ #
    async def _apply_corrections(
        self, tender_id: UUID, corrections: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not corrections:
            return {}, {}
        unknown_fields = set(corrections) - set(METADATA_FIELDS)
        if unknown_fields:
            raise DomainValidationError(f"unknown metadata fields: {sorted(unknown_fields)}")

        metadata = await self._metadata_repo.get_for_tender(tender_id)
        if metadata is None:
            raise DomainValidationError("no extracted metadata to correct")

        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        for field_name, raw in corrections.items():
            current: ExtractedField[Any] = getattr(metadata, field_name)
            before[field_name] = _serialise(current.value)
            coerced = _coerce(field_name, raw)
            setattr(
                metadata,
                field_name,
                ExtractedField.known(coerced, 1.0, source=_CORRECTION_SOURCE),
            )
            after[field_name] = _serialise(coerced)

        # Stamp the change: this timestamp is what tells a later reader that a
        # recorded verdict now rests on evidence that has moved.
        metadata.touch()
        await self._metadata_repo.upsert(metadata)
        return before, after

    async def _require_tender(self, tender_id: UUID) -> Tender:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            raise EntityNotFoundError("Tender", tender_id)
        return tender

    async def _audit(
        self,
        reviewer_id: UUID,
        tender_id: UUID,
        action: str,
        verdict: ReviewVerdict | None,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        diff: dict[str, Any] = {}
        if verdict is not None:
            diff["verdict"] = verdict.value
        for field_name in after:
            diff[field_name] = {"before": before.get(field_name), "after": after[field_name]}
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type="Tender",
                entity_id=str(tender_id),
                actor_id=reviewer_id,
                diff=diff,
            )
        )


def _coerce(field_name: str, raw: str) -> Any:
    value = raw.strip()
    if field_name in _DECIMAL_FIELDS:
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise DomainValidationError(f"{field_name} must be a number") from exc
    if field_name in _DATE_FIELDS:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise DomainValidationError(f"{field_name} must be an ISO date") from exc
    return value


def _serialise(value: Any) -> Any:
    if not is_known(value):
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
