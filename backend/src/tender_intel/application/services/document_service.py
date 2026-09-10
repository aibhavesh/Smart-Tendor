"""Document pipeline use cases (FR-101..FR-126).

Registers documents (by URL for background download, or by direct upload),
downloads + hashes + stores them, tracks attempts/errors, supports manual
re-trigger, and advances the tender lifecycle to DOWNLOADED on first success.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from uuid import UUID, uuid4

from tender_intel.domain.entities import AuditLog, TenderDocument
from tender_intel.domain.enums.document_status import DocumentStatus
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import EntityNotFoundError
from tender_intel.domain.interfaces.providers import Downloader, FileStorage
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    TenderDocumentRepository,
    TenderRepository,
)
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str | None, fallback_id: UUID, mime: str | None) -> str:
    if name:
        cleaned = _UNSAFE.sub("_", name.rsplit("/", 1)[-1]).strip("_")
        if cleaned:
            return cleaned[:200]
    ext = mimetypes.guess_extension(mime or "") or ".bin"
    return f"{fallback_id}{ext}"


class DocumentService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        documents: TenderDocumentRepository,
        audits: AuditLogRepository,
        downloader: Downloader,
        storage: FileStorage,
    ) -> None:
        self._tenders = tenders
        self._documents = documents
        self._audits = audits
        self._downloader = downloader
        self._storage = storage

    async def add_from_url(
        self, tender_id: UUID, url: str, *, actor_id: UUID | None = None
    ) -> TenderDocument:
        await self._require_tender(tender_id)
        document = await self._documents.add(
            TenderDocument(tender_id=tender_id, source_url=url, status=DocumentStatus.PENDING)
        )
        await self._audit(actor_id, "document.add", document.id)
        return document

    async def upload(
        self,
        tender_id: UUID,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None,
        actor_id: UUID | None = None,
    ) -> TenderDocument:
        await self._require_tender(tender_id)
        document = TenderDocument(tender_id=tender_id, status=DocumentStatus.PENDING)
        await self._store(document, content, filename, mime_type)
        stored = await self._documents.add(document)
        await self._advance_tender(tender_id)
        await self._audit(actor_id, "document.upload", stored.id)
        return stored

    async def list_for_tender(self, tender_id: UUID) -> list[TenderDocument]:
        await self._require_tender(tender_id)
        return await self._documents.list_for_tender(tender_id)

    async def get_or_404(self, document_id: UUID) -> TenderDocument:
        document = await self._documents.get(document_id)
        if document is None:
            raise EntityNotFoundError("TenderDocument", document_id)
        return document

    async def retrigger(self, document_id: UUID, *, actor_id: UUID | None = None) -> TenderDocument:
        document = await self.get_or_404(document_id)
        document.status = DocumentStatus.PENDING
        document.last_error = None
        updated = await self._documents.update(document)
        await self._audit(actor_id, "document.retrigger", document_id)
        return updated

    async def process_pending(self, limit: int = 10) -> int:
        """Download one batch of PENDING documents. Returns the count processed."""
        pending = await self._documents.list_by_status(DocumentStatus.PENDING, limit)
        for document in pending:
            await self._download_one(document)
        return len(pending)

    # ------------------------------------------------------------------ #
    async def _download_one(self, document: TenderDocument) -> None:
        if not document.source_url:
            document.mark_failed("no source URL")
            await self._documents.update(document)
            return
        document.mark_downloading()
        await self._documents.update(document)
        try:
            result = await self._downloader.download(document.source_url)
            await self._store(document, result.content, result.suggested_name, result.mime_type)
            await self._documents.update(document)
            await self._advance_tender(document.tender_id)
            _log.info("document.downloaded", document_id=str(document.id))
        except Exception as exc:
            document.mark_failed(str(exc))
            await self._documents.update(document)
            _log.warning("document.failed", document_id=str(document.id), error=str(exc))

    async def _store(
        self, document: TenderDocument, content: bytes, name: str | None, mime: str | None
    ) -> None:
        filename = _safe_name(name, uuid4(), mime)
        sha256 = hashlib.sha256(content).hexdigest()
        path = f"tenders/{document.tender_id}/{document.id}/{filename}"
        stored_path = await self._storage.save(path, content)
        document.mark_downloaded(
            file_name=filename,
            file_path=stored_path,
            file_size=len(content),
            mime_type=mime or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            sha256=sha256,
        )

    async def _advance_tender(self, tender_id: UUID) -> None:
        tender = await self._tenders.get(tender_id)
        if tender is not None and tender.status is TenderStatus.REGISTERED:
            tender.transition_to(TenderStatus.DOWNLOADED)
            await self._tenders.update(tender)

    async def _require_tender(self, tender_id: UUID) -> None:
        if await self._tenders.get(tender_id) is None:
            raise EntityNotFoundError("Tender", tender_id)

    async def _audit(self, actor_id: UUID | None, action: str, document_id: UUID) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type="TenderDocument",
                entity_id=str(document_id),
                actor_id=actor_id,
            )
        )
