"""TenderDocument entity — one downloadable/attached file for a tender."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tender_intel.domain.enums.document_status import DocumentStatus


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class TenderDocument:
    tender_id: UUID
    source_url: str | None = None  # None for direct uploads
    file_name: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    sha256: str | None = None
    status: DocumentStatus = DocumentStatus.PENDING
    attempt_count: int = 0
    last_error: str | None = None
    downloaded_at: datetime | None = None
    raw_text: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def mark_downloading(self) -> None:
        self.status = DocumentStatus.DOWNLOADING
        self.attempt_count += 1
        self.updated_at = _now()

    def mark_downloaded(
        self, *, file_name: str, file_path: str, file_size: int, mime_type: str, sha256: str
    ) -> None:
        self.status = DocumentStatus.DOWNLOADED
        self.file_name = file_name
        self.file_path = file_path
        self.file_size = file_size
        self.mime_type = mime_type
        self.sha256 = sha256
        self.last_error = None
        self.downloaded_at = _now()
        self.updated_at = _now()

    def mark_failed(self, error: str) -> None:
        self.status = DocumentStatus.FAILED
        self.last_error = error
        self.updated_at = _now()
