"""Background document-download worker (15-second poll, FR-101..FR-126).

Owns its own session per batch (it is not request-scoped) and commits after each
batch so partial progress survives a crash. ``run_once`` is the unit under test;
``run_forever`` is the loop started from the API lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tender_intel.application.services.document_service import DocumentService
from tender_intel.domain.interfaces.providers import Downloader, FileStorage
from tender_intel.infrastructure.observability.logging import get_logger
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyTenderDocumentRepository,
    SqlAlchemyTenderRepository,
)

_log = get_logger(__name__)


class DocumentDownloadWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        downloader: Downloader,
        storage: FileStorage,
        poll_seconds: int = 15,
        batch_size: int = 10,
    ) -> None:
        self._session_factory = session_factory
        self._downloader = downloader
        self._storage = storage
        self._poll_seconds = poll_seconds
        self._batch_size = batch_size

    async def run_once(self) -> int:
        async with self._session_factory() as session:
            service = DocumentService(
                tenders=SqlAlchemyTenderRepository(session),
                documents=SqlAlchemyTenderDocumentRepository(session),
                audits=SqlAlchemyAuditLogRepository(session),
                downloader=self._downloader,
                storage=self._storage,
            )
            processed = await service.process_pending(self._batch_size)
            await session.commit()
            return processed

    async def run_forever(self) -> None:
        _log.info("document_worker.started", poll_seconds=self._poll_seconds)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                _log.info("document_worker.stopped")
                raise
            except Exception as exc:
                _log.error("document_worker.batch_error", error=str(exc))
            await asyncio.sleep(self._poll_seconds)


def start_worker(worker: DocumentDownloadWorker) -> asyncio.Task[None]:
    return asyncio.create_task(worker.run_forever())


async def stop_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
