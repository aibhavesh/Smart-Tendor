"""Phase 4 extraction tests: service end-to-end and API surface."""

from __future__ import annotations

from decimal import Decimal

from tender_intel.application.services.document_service import DocumentService
from tender_intel.application.services.extraction_service import ExtractionService
from tender_intel.domain.entities import Tender
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.infrastructure.extraction.rule_metadata import RuleBasedMetadataExtractor
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyBOQItemRepository,
    SqlAlchemyTenderDocumentRepository,
    SqlAlchemyTenderMetadataRepository,
    SqlAlchemyTenderRepository,
)
from tests.integration.helpers import auth_headers

SAMPLE_TEXT = (
    b"Name of Work: RCC Drain\nEstimated Cost: Rs. 2 Crore\nEMD: Rs. 2,00,000\n"
    b"Last Date of Submission: 01/10/2026\nLocation: Bhopal\n"
)


class MemoryStorage:
    def __init__(self, data: dict[str, bytes] | None = None):
        self.files = data or {}

    async def save(self, relative_path: str, content: bytes) -> str:
        self.files[relative_path] = content
        return relative_path

    async def read(self, relative_path: str) -> bytes:
        return self.files[relative_path]

    async def delete(self, relative_path: str) -> None:
        self.files.pop(relative_path, None)


class PlainTextExtractor:
    def extract_text(self, content: bytes) -> str:
        return content.decode("utf-8")


class FakeTableExtractor:
    def __init__(self, tables):
        self._tables = tables

    def extract_tables(self, content: bytes):
        return self._tables


class NoopDownloader:
    async def download(self, url: str):  # pragma: no cover - not used
        raise NotImplementedError


async def _seed_downloaded_pdf(session, storage) -> Tender:
    tenders = SqlAlchemyTenderRepository(session)
    tender = await tenders.add(Tender(tender_number="T-EX", title="Drain"))
    docs = DocumentService(
        tenders=tenders,
        documents=SqlAlchemyTenderDocumentRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
        downloader=NoopDownloader(),
        storage=storage,
    )
    # Direct upload marks the document DOWNLOADED and advances tender.
    await docs.upload(
        tender.id, filename="tender.pdf", content=SAMPLE_TEXT, mime_type="application/pdf"
    )
    return tender


def _extraction_service(session, storage, tables) -> ExtractionService:
    return ExtractionService(
        tenders=SqlAlchemyTenderRepository(session),
        documents=SqlAlchemyTenderDocumentRepository(session),
        metadata_repo=SqlAlchemyTenderMetadataRepository(session),
        boq_repo=SqlAlchemyBOQItemRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
        storage=storage,
        text_extractor=PlainTextExtractor(),
        table_extractor=FakeTableExtractor(tables),
        metadata_backend=RuleBasedMetadataExtractor(),
    )


async def test_extraction_populates_metadata_boq_and_parses(session):
    storage = MemoryStorage()
    tender = await _seed_downloaded_pdf(session, storage)

    tables = [
        [
            ["Description", "Unit", "Quantity", "Rate", "Amount"],
            ["Excavation", "Cum", "100", "50", "5000"],
        ]
    ]
    service = _extraction_service(session, storage, tables)
    result = await service.extract(tender.id)

    # Metadata extracted from the document text.
    assert result.metadata.work_name.value == "RCC Drain"
    assert result.metadata.estimated_value.value == Decimal("20000000")
    assert result.metadata.emd_amount.value == Decimal("200000")

    # BOQ extracted from the (faked) tables.
    assert len(result.boq_items) == 1
    assert result.boq_items[0].amount == Decimal("5000")

    # Tender advanced to PARSED.
    refreshed = await SqlAlchemyTenderRepository(session).get(tender.id)
    assert refreshed.status is TenderStatus.PARSED


async def test_re_extraction_replaces_boq(session):
    storage = MemoryStorage()
    tender = await _seed_downloaded_pdf(session, storage)

    first = _extraction_service(
        session,
        storage,
        [[["Description", "Amount"], ["A", "100"], ["B", "200"]]],
    )
    await first.extract(tender.id)
    boq_repo = SqlAlchemyBOQItemRepository(session)
    assert len(await boq_repo.list_for_tender(tender.id)) == 2

    second = _extraction_service(session, storage, [[["Description", "Amount"], ["C", "300"]]])
    await second.extract(tender.id)
    items = await boq_repo.list_for_tender(tender.id)
    assert len(items) == 1
    assert items[0].description == "C"


async def test_extract_without_downloaded_document_errors(session):
    from tender_intel.domain.exceptions import DomainValidationError

    tender = await SqlAlchemyTenderRepository(session).add(
        Tender(tender_number="T-NODOC", title="X")
    )
    service = _extraction_service(session, MemoryStorage(), [])
    try:
        await service.extract(tender.id)
        raise AssertionError("expected DomainValidationError")
    except DomainValidationError:
        pass


# --- API ---
async def test_extract_api_flow(client, app_db):
    headers = await auth_headers(client, app_db)
    tender = (
        await client.post(
            "/tenders", json={"tender_number": "T-API", "title": "T"}, headers=headers
        )
    ).json()
    # Upload a text document (mime text/plain -> decoded, no PDF tables).
    await client.post(
        f"/tenders/{tender['id']}/documents/upload",
        files={"file": ("info.txt", SAMPLE_TEXT, "text/plain")},
        headers=headers,
    )

    extracted = await client.post(f"/tenders/{tender['id']}/extract", headers=headers)
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["status"] == "PARSED"
    assert body["metadata"]["fields"]["work_name"]["value"] == "RCC Drain"
    assert body["metadata"]["fields"]["estimated_value"]["value"] == "20000000"
    assert body["metadata"]["fields"]["scope_of_work"]["is_known"] is False

    meta = await client.get(f"/tenders/{tender['id']}/metadata", headers=headers)
    assert meta.status_code == 200

    analytics = await client.get(f"/tenders/{tender['id']}/boq/analytics", headers=headers)
    assert analytics.status_code == 200
    assert analytics.json()["total_items"] == 0  # no tables in a text upload
