"""Tender request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from tender_intel.application.dto.ingestion import (
    BulkImportResult,
    RowResult,
    TenderCreate,
    TenderPatch,
)
from tender_intel.domain.entities import Tender
from tender_intel.domain.enums.tender_status import TenderStatus


class TenderCreateRequest(BaseModel):
    tender_number: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=1024)
    description: str | None = None
    estimated_value: Decimal | None = Field(default=None, ge=0)
    closing_date: date | None = None
    source_url: str | None = None
    department: str | None = None

    def to_dto(self) -> TenderCreate:
        return TenderCreate(
            tender_number=self.tender_number.strip(),
            title=self.title.strip(),
            description=self.description,
            estimated_value=self.estimated_value,
            closing_date=self.closing_date,
            source_url=self.source_url,
            department=self.department,
        )


class TenderPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=1024)
    description: str | None = None
    estimated_value: Decimal | None = Field(default=None, ge=0)
    closing_date: date | None = None
    source_url: str | None = None
    department: str | None = None

    def to_dto(self) -> TenderPatch:
        return TenderPatch(
            title=self.title,
            description=self.description,
            estimated_value=self.estimated_value,
            closing_date=self.closing_date,
            source_url=self.source_url,
            department=self.department,
        )


class TenderResponse(BaseModel):
    id: UUID
    tender_number: str
    title: str
    status: TenderStatus  # lifecycle status on every representation
    description: str | None
    estimated_value: Decimal | None
    closing_date: date | None
    source_url: str | None
    department: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, tender: Tender) -> TenderResponse:
        return cls(
            id=tender.id,
            tender_number=tender.tender_number,
            title=tender.title,
            status=tender.status,
            description=tender.description,
            estimated_value=tender.estimated_value,
            closing_date=tender.closing_date,
            source_url=tender.source_url,
            department=tender.department,
            created_at=tender.created_at,
            updated_at=tender.updated_at,
        )


class ImportRowResponse(BaseModel):
    row: int
    tender_number: str | None
    outcome: str
    message: str | None

    @classmethod
    def from_dto(cls, r: RowResult) -> ImportRowResponse:
        return cls(
            row=r.row, tender_number=r.tender_number, outcome=r.outcome.value, message=r.message
        )


class BulkImportResponse(BaseModel):
    created: int
    skipped: int
    errors: int
    queued_documents: int = 0
    results: list[ImportRowResponse]

    @classmethod
    def from_dto(cls, result: BulkImportResult) -> BulkImportResponse:
        return cls(
            created=result.created,
            skipped=result.skipped,
            errors=result.errors,
            queued_documents=result.queued_documents,
            results=[ImportRowResponse.from_dto(r) for r in result.results],
        )
