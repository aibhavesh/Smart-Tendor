"""Past-project request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from tender_intel.application.dto.past_project import PastProjectCreate, PastProjectPatch
from tender_intel.domain.entities import PastProject


class PastProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=1024)
    client: str | None = None
    work_value: Decimal | None = Field(default=None, ge=0)
    category: str | None = None
    location: str | None = None
    description: str | None = None
    completion_date: date | None = None

    def to_dto(self) -> PastProjectCreate:
        return PastProjectCreate(
            name=self.name.strip(),
            client=self.client,
            work_value=self.work_value,
            category=self.category,
            location=self.location,
            description=self.description,
            completion_date=self.completion_date,
        )


class PastProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=1024)
    client: str | None = None
    work_value: Decimal | None = Field(default=None, ge=0)
    category: str | None = None
    location: str | None = None
    description: str | None = None
    completion_date: date | None = None

    def to_dto(self) -> PastProjectPatch:
        return PastProjectPatch(
            name=self.name,
            client=self.client,
            work_value=self.work_value,
            category=self.category,
            location=self.location,
            description=self.description,
            completion_date=self.completion_date,
        )


class PastProjectResponse(BaseModel):
    id: UUID
    name: str
    client: str | None
    work_value: Decimal | None
    category: str | None
    location: str | None
    description: str | None
    completion_date: date | None
    embedding_indexed: bool
    created_at: datetime

    @classmethod
    def from_entity(cls, p: PastProject) -> PastProjectResponse:
        return cls(
            id=p.id,
            name=p.name,
            client=p.client,
            work_value=p.work_value,
            category=p.category,
            location=p.location,
            description=p.description,
            completion_date=p.completion_date,
            embedding_indexed=p.embedding_indexed,
            created_at=p.created_at,
        )


class BackfillResponse(BaseModel):
    indexed: int
