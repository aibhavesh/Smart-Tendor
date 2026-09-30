"""Automatic extraction and eligibility screening for downloaded tenders.

The ingestion worker owns network download only. This worker completes the
workflow once bytes are available: ``DOWNLOADED -> PARSED -> eligibility``.
It intentionally has no HTTP surface, so every import follows the same path.
"""

from __future__ import annotations

import asyncio
import contextlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tender_intel.application.services.eligibility_service import EligibilityService
from tender_intel.application.services.extraction_service import ExtractionService
from tender_intel.core.config import Settings
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.interfaces.providers import EmbeddingProvider, VectorStore
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.extraction.pdf_backends import (
    PdfPlumberBOQExtractor,
    resolve_text_extractor,
)
from tender_intel.infrastructure.extraction.rule_metadata import RuleBasedMetadataExtractor
from tender_intel.infrastructure.observability.logging import get_logger
from tender_intel.infrastructure.repositories.eligibility_repo import (
    SqlAlchemyCompanyTurnoverRepository,
    SqlAlchemyPortfolioVersionRepository,
    SqlAlchemyTenderEligibilityRepository,
)
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyBOQItemRepository,
    SqlAlchemyTenderDocumentRepository,
    SqlAlchemyTenderMetadataRepository,
    SqlAlchemyTenderRepository,
)
from tender_intel.infrastructure.repositories.work_type_repo import SqlAlchemyWorkTypeRepository
from tender_intel.infrastructure.storage import LocalFileStorage

_log = get_logger(__name__)


class _NoOpAuditLogRepository:
    async def add(self, entry: object) -> None:
        del entry


class EligibilityWorkflowWorker:
    """Runs extraction and screening for a bounded batch of downloaded tenders."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        embeddings: EmbeddingProvider,
        vectors: VectorStore,
        poll_seconds: int = 15,
        batch_size: int = 10,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._embeddings = embeddings
        self._vectors = vectors
        self._poll_seconds = poll_seconds
        self._batch_size = batch_size
        self._storage = LocalFileStorage(settings.storage_dir)
        self._text_extractor = resolve_text_extractor(settings.extraction_text_backend)
        self._table_extractor = PdfPlumberBOQExtractor()
        self._metadata_backend = RuleBasedMetadataExtractor()

    async def run_once(self) -> int:
        tender_ids = await self._downloaded_tender_ids()
        completed = 0
        for tender_id in tender_ids:
            try:
                await self._extract_and_screen(tender_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("eligibility_workflow.failed", tender_id=str(tender_id))
            else:
                completed += 1
                _log.info("eligibility_workflow.completed", tender_id=str(tender_id))
        return completed

    async def run_forever(self) -> None:
        _log.info("eligibility_workflow.started", poll_seconds=self._poll_seconds)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                _log.info("eligibility_workflow.stopped")
                raise
            except Exception:
                _log.exception("eligibility_workflow.batch_error")
            await asyncio.sleep(self._poll_seconds)

    async def _downloaded_tender_ids(self) -> list[UUID]:
        async with self._session_factory() as session:
            page = await SqlAlchemyTenderRepository(session).list(
                PageRequest(limit=self._batch_size), status=TenderStatus.DOWNLOADED
            )
            return [tender.id for tender in page.items]

    async def _extract_and_screen(self, tender_id: UUID) -> None:
        async with self._session_factory() as session:
            tenders = SqlAlchemyTenderRepository(session)
            metadata = SqlAlchemyTenderMetadataRepository(session)
            audits = _NoOpAuditLogRepository()
            extraction = ExtractionService(
                tenders=tenders,
                documents=SqlAlchemyTenderDocumentRepository(session),
                metadata_repo=metadata,
                boq_repo=SqlAlchemyBOQItemRepository(session),
                audits=audits,
                storage=self._storage,
                text_extractor=self._text_extractor,
                table_extractor=self._table_extractor,
                metadata_backend=self._metadata_backend,
            )
            await extraction.extract(tender_id)
            eligibility = EligibilityService(
                tenders=tenders,
                metadata_repo=metadata,
                projects=SqlAlchemyPastProjectRepository(session),
                work_types=SqlAlchemyWorkTypeRepository(session),
                turnover=SqlAlchemyCompanyTurnoverRepository(session),
                results=SqlAlchemyTenderEligibilityRepository(session),
                versions=SqlAlchemyPortfolioVersionRepository(session),
                audits=audits,
                embeddings=self._embeddings,
                vectors=self._vectors,
                collection=self._settings.qdrant_collection,
            )
            await eligibility.screen(tender_id)
            await session.commit()


def start_workflow_worker(worker: EligibilityWorkflowWorker) -> asyncio.Task[None]:
    return asyncio.create_task(worker.run_forever())


async def stop_workflow_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
