"""Extraction use cases (FR-201..FR-215).

Turns a DOWNLOADED document into structured, decision-ready data: the ten
metadata fields (with confidence + UNKNOWN) and table-aware BOQ line items, then
advances the tender to PARSED. CPU-bound PDF parsing runs in a worker thread.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from tender_intel.domain.entities import BOQItem, TenderDocument, TenderMetadata
from tender_intel.domain.entities.audit import AuditLog
from tender_intel.domain.enums.document_status import DocumentStatus
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import DomainValidationError, EntityNotFoundError
from tender_intel.domain.interfaces.providers import (
    BOQTableExtractor,
    DocumentTextExtractor,
    FileStorage,
    MetadataExtractionBackend,
)
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    BOQItemRepository,
    TenderDocumentRepository,
    TenderMetadataRepository,
    TenderRepository,
)
from tender_intel.infrastructure.extraction.boq_parser import parse_boq_tables


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    metadata: TenderMetadata
    boq_items: list[BOQItem]


def _is_pdf(document: TenderDocument) -> bool:
    if document.mime_type and "pdf" in document.mime_type.lower():
        return True
    return bool(document.file_name and document.file_name.lower().endswith(".pdf"))


class ExtractionService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        documents: TenderDocumentRepository,
        metadata_repo: TenderMetadataRepository,
        boq_repo: BOQItemRepository,
        audits: AuditLogRepository,
        storage: FileStorage,
        text_extractor: DocumentTextExtractor,
        table_extractor: BOQTableExtractor,
        metadata_backend: MetadataExtractionBackend,
    ) -> None:
        self._tenders = tenders
        self._documents = documents
        self._metadata_repo = metadata_repo
        self._boq_repo = boq_repo
        self._audits = audits
        self._storage = storage
        self._text_extractor = text_extractor
        self._table_extractor = table_extractor
        self._metadata_backend = metadata_backend

    async def extract(
        self,
        tender_id: UUID,
        *,
        document_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> ExtractionResult:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            raise EntityNotFoundError("Tender", tender_id)
        document = await self._select_document(tender_id, document_id)

        content = await self._storage.read(document.file_path or "")
        text = await self._extract_text(document, content)

        # --- Metadata (the ten fields) ---
        fields = self._metadata_backend.extract(text)
        metadata = TenderMetadata(tender_id=tender_id, raw_text=text)
        for name, field in fields.items():
            setattr(metadata, name, field)
        stored_metadata = await self._metadata_repo.upsert(metadata)

        # --- BOQ (table-aware) ---
        tables = (
            await asyncio.to_thread(self._table_extractor.extract_tables, content)
            if _is_pdf(document)
            else []
        )
        boq_items = parse_boq_tables(tables, tender_id)
        await self._boq_repo.delete_for_tender(tender_id)  # re-extraction replaces
        stored_items = await self._boq_repo.add_many(boq_items) if boq_items else []

        # --- Retain raw text on the document; advance lifecycle to PARSED ---
        document.raw_text = text
        await self._documents.update(document)
        await self._advance_to_parsed(tender_id)

        await self._audit(actor_id, tender_id, len(stored_items))
        return ExtractionResult(metadata=stored_metadata, boq_items=stored_items)

    # ------------------------------------------------------------------ #
    async def _select_document(self, tender_id: UUID, document_id: UUID | None) -> TenderDocument:
        if document_id is not None:
            document = await self._documents.get(document_id)
            if document is None or document.tender_id != tender_id:
                raise EntityNotFoundError("TenderDocument", document_id)
            if document.status is not DocumentStatus.DOWNLOADED:
                raise DomainValidationError("document is not DOWNLOADED")
            return document
        for candidate in await self._documents.list_for_tender(tender_id):
            if candidate.status is DocumentStatus.DOWNLOADED:
                return candidate
        raise DomainValidationError("no DOWNLOADED document available to extract")

    async def _extract_text(self, document: TenderDocument, content: bytes) -> str:
        if _is_pdf(document):
            return await asyncio.to_thread(self._text_extractor.extract_text, content)
        return content.decode("utf-8", errors="ignore")

    async def _advance_to_parsed(self, tender_id: UUID) -> None:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            return
        if tender.status is not TenderStatus.PARSED and tender.status.can_transition_to(
            TenderStatus.PARSED
        ):
            tender.transition_to(TenderStatus.PARSED)
            await self._tenders.update(tender)

    async def _audit(self, actor_id: UUID | None, tender_id: UUID, boq_count: int) -> None:
        await self._audits.add(
            AuditLog(
                action="tender.extract",
                entity_type="Tender",
                entity_id=str(tender_id),
                actor_id=actor_id,
                diff={"boq_items": boq_count},
            )
        )
