"""Tender registry & bulk import use cases (FR-101..FR-126)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from tender_intel.application.dto.ingestion import (
    BulkImportResult,
    ImportOutcome,
    RowResult,
    TenderCreate,
    TenderPatch,
)
from tender_intel.application.services.document_service import DocumentService
from tender_intel.domain.entities import AuditLog, Tender
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import DuplicateEntityError, EntityNotFoundError
from tender_intel.domain.interfaces.repositories import AuditLogRepository, TenderRepository
from tender_intel.domain.value_objects.pagination import Page, PageRequest


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", "").replace("₹", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


class TenderService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        audits: AuditLogRepository,
        documents: DocumentService | None = None,
    ) -> None:
        self._tenders = tenders
        self._audits = audits
        # Optional so the registry use cases stay usable without the document
        # pipeline wired in (the unit tests construct it that way). When it is
        # present, bulk_import queues each row's linked document for download.
        self._documents = documents

    async def create(self, data: TenderCreate, *, actor_id: UUID | None = None) -> Tender:
        if await self._tenders.exists_number(data.tender_number):
            raise DuplicateEntityError("Tender", "tender_number", data.tender_number)
        tender = Tender(
            tender_number=data.tender_number,
            title=data.title,
            description=data.description,
            estimated_value=data.estimated_value,
            closing_date=data.closing_date,
            source_url=data.source_url,
            department=data.department,
        )
        created = await self._tenders.add(tender)
        await self._audit(actor_id, "tender.create", created.id)
        return created

    async def get_or_404(self, tender_id: UUID) -> Tender:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            raise EntityNotFoundError("Tender", tender_id)
        return tender

    async def list(
        self,
        page: PageRequest,
        *,
        status: TenderStatus | None = None,
        search: str | None = None,
    ) -> Page[Tender]:
        return await self._tenders.list(page, status=status, search=search)

    async def patch(
        self, tender_id: UUID, data: TenderPatch, *, actor_id: UUID | None = None
    ) -> Tender:
        tender = await self.get_or_404(tender_id)
        diff: dict[str, Any] = {}
        for field_name in (
            "title",
            "description",
            "estimated_value",
            "closing_date",
            "source_url",
            "department",
        ):
            new_value = getattr(data, field_name)
            if new_value is not None:
                old_value = getattr(tender, field_name)
                if old_value != new_value:
                    diff[field_name] = {"before": _json(old_value), "after": _json(new_value)}
                    setattr(tender, field_name, new_value)
        if not diff:
            return tender
        updated = await self._tenders.update(tender)
        await self._audit(actor_id, "tender.update", tender_id, diff)
        return updated

    async def delete(self, tender_id: UUID, *, actor_id: UUID | None = None) -> None:
        await self.get_or_404(tender_id)
        await self._tenders.delete(tender_id)
        await self._audit(actor_id, "tender.delete", tender_id)

    async def bulk_import(
        self, rows: Iterable[tuple[int, dict[str, Any]]], *, actor_id: UUID | None = None
    ) -> BulkImportResult:
        result = BulkImportResult()
        for row_number, record in rows:
            number = str(record.get("tender_number") or "").strip()
            title = str(record.get("title") or "").strip()
            if not number or not title:
                result.results.append(
                    RowResult(
                        row_number,
                        number or None,
                        ImportOutcome.ERROR,
                        "tender_number and title are required",
                    )
                )
                continue
            if await self._tenders.exists_number(number):
                result.results.append(
                    RowResult(row_number, number, ImportOutcome.SKIPPED, "already exists")
                )
                continue
            source_url = str(record["source_url"]).strip() if record.get("source_url") else None
            try:
                created = await self._tenders.add(
                    Tender(
                        tender_number=number,
                        title=title,
                        description=(
                            str(record["description"]).strip()
                            if record.get("description")
                            else None
                        ),
                        estimated_value=_to_decimal(record.get("estimated_value")),
                        closing_date=_to_date(record.get("closing_date")),
                        source_url=source_url,
                        department=(
                            str(record["department"]).strip() if record.get("department") else None
                        ),
                    )
                )
                # Queue the linked document so the download worker fetches it and
                # advances the tender REGISTERED -> DOWNLOADED, which is what the
                # extraction and decision stages wait on. A failure here must not
                # lose the tender that was just imported, so it is reported on the
                # row rather than raised.
                note: str | None = None
                if source_url and self._documents is not None:
                    try:
                        await self._documents.add_from_url(
                            created.id, source_url, actor_id=actor_id
                        )
                        result.queued_documents += 1
                        note = "document queued for download"
                    except Exception as exc:
                        note = f"tender imported but document not queued: {exc}"
                result.results.append(RowResult(row_number, number, ImportOutcome.CREATED, note))
            except Exception as exc:
                result.results.append(RowResult(row_number, number, ImportOutcome.ERROR, str(exc)))
        await self._audit(
            actor_id,
            "tender.bulk_import",
            None,
            {
                "created": result.created,
                "skipped": result.skipped,
                "errors": result.errors,
                "queued_documents": result.queued_documents,
            },
        )
        return result

    async def _audit(
        self,
        actor_id: UUID | None,
        action: str,
        entity_id: UUID | None,
        diff: dict[str, Any] | None = None,
    ) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type="Tender",
                entity_id=str(entity_id) if entity_id else None,
                actor_id=actor_id,
                diff=diff or {},
            )
        )


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
