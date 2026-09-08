"""Phase 3 document-pipeline tests: worker download, hashing, lifecycle, retrigger."""

from __future__ import annotations

import hashlib

import pytest

from tender_intel.application.services.document_service import DocumentService
from tender_intel.domain.entities import Tender
from tender_intel.domain.enums.document_status import DocumentStatus
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.interfaces.providers import DownloadResult
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyTenderDocumentRepository,
    SqlAlchemyTenderRepository,
)


class FakeDownloader:
    def __init__(self, content=b"PDF-BYTES", *, fail=False):
        self.content = content
        self.fail = fail

    async def download(self, url: str) -> DownloadResult:
        if self.fail:
            raise RuntimeError("network down")
        return DownloadResult(
            content=self.content, mime_type="application/pdf", suggested_name="tender.pdf"
        )


class MemoryStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    async def save(self, relative_path: str, content: bytes) -> str:
        self.files[relative_path] = content
        return relative_path

    async def read(self, relative_path: str) -> bytes:
        return self.files[relative_path]

    async def delete(self, relative_path: str) -> None:
        self.files.pop(relative_path, None)


def _service(session, downloader, storage) -> DocumentService:
    return DocumentService(
        tenders=SqlAlchemyTenderRepository(session),
        documents=SqlAlchemyTenderDocumentRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
        downloader=downloader,
        storage=storage,
    )


async def _tender(session) -> Tender:
    return await SqlAlchemyTenderRepository(session).add(Tender(tender_number="T-1", title="Road"))


async def test_worker_downloads_hashes_and_advances_lifecycle(session):
    tender = await _tender(session)
    storage = MemoryStorage()
    content = b"THE-DOCUMENT"
    service = _service(session, FakeDownloader(content), storage)

    doc = await service.add_from_url(tender.id, "https://example.com/t.pdf")
    assert doc.status is DocumentStatus.PENDING

    processed = await service.process_pending()
    assert processed == 1

    stored = await service.get_or_404(doc.id)
    assert stored.status is DocumentStatus.DOWNLOADED
    assert stored.sha256 == hashlib.sha256(content).hexdigest()
    assert stored.file_size == len(content)
    assert stored.attempt_count == 1
    assert storage.files  # bytes actually persisted

    # Tender advanced REGISTERED -> DOWNLOADED on first successful download.
    refreshed = await SqlAlchemyTenderRepository(session).get(tender.id)
    assert refreshed.status is TenderStatus.DOWNLOADED


async def test_failed_download_records_error_then_retrigger_succeeds(session):
    tender = await _tender(session)
    storage = MemoryStorage()
    service = _service(session, FakeDownloader(fail=True), storage)
    doc = await service.add_from_url(tender.id, "https://example.com/t.pdf")

    await service.process_pending()
    failed = await service.get_or_404(doc.id)
    assert failed.status is DocumentStatus.FAILED
    assert failed.last_error == "network down"
    assert failed.attempt_count == 1

    # Swap in a working downloader and re-trigger.
    service._downloader = FakeDownloader(b"OK")
    retried = await service.retrigger(doc.id)
    assert retried.status is DocumentStatus.PENDING
    assert retried.last_error is None

    await service.process_pending()
    recovered = await service.get_or_404(doc.id)
    assert recovered.status is DocumentStatus.DOWNLOADED
    assert recovered.attempt_count == 2  # attempts accumulate across retries


async def test_direct_upload_is_immediately_downloaded(session):
    tender = await _tender(session)
    service = _service(session, FakeDownloader(), MemoryStorage())

    doc = await service.upload(
        tender.id, filename="boq.xlsx", content=b"SHEET", mime_type="application/xlsx"
    )
    assert doc.status is DocumentStatus.DOWNLOADED
    assert doc.sha256 == hashlib.sha256(b"SHEET").hexdigest()

    refreshed = await SqlAlchemyTenderRepository(session).get(tender.id)
    assert refreshed.status is TenderStatus.DOWNLOADED


async def test_add_document_to_missing_tender_404s(session):
    from uuid import uuid4

    from tender_intel.domain.exceptions import EntityNotFoundError

    service = _service(session, FakeDownloader(), MemoryStorage())
    with pytest.raises(EntityNotFoundError):
        await service.add_from_url(uuid4(), "https://example.com/x.pdf")
