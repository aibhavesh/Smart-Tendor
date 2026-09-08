"""Tender-document request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from tender_intel.domain.entities import TenderDocument
from tender_intel.domain.enums.document_status import DocumentStatus


class DocumentFromUrlRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=2048)


class DocumentResponse(BaseModel):
    id: UUID
    tender_id: UUID
    source_url: str | None
    file_name: str | None
    file_path: str | None
    file_size: int | None
    mime_type: str | None
    sha256: str | None
    status: DocumentStatus
    attempt_count: int
    last_error: str | None
    downloaded_at: datetime | None
    created_at: datetime

    @classmethod
    def from_entity(cls, doc: TenderDocument) -> DocumentResponse:
        return cls(
            id=doc.id,
            tender_id=doc.tender_id,
            source_url=doc.source_url,
            file_name=doc.file_name,
            file_path=doc.file_path,
            file_size=doc.file_size,
            mime_type=doc.mime_type,
            sha256=doc.sha256,
            status=doc.status,
            attempt_count=doc.attempt_count,
            last_error=doc.last_error,
            downloaded_at=doc.downloaded_at,
            created_at=doc.created_at,
        )
