"""Work-type taxonomy and certified-turnover schemas (feature spec §8)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from tender_intel.domain.entities.company_turnover import CompanyTurnover
from tender_intel.domain.entities.work_type import (
    PastProjectWorkType,
    WorkType,
    WorkTypeAlias,
)
from tender_intel.domain.enums.work_type import (
    AliasKind,
    WorkTypeCategory,
    WorkTypeLinkSource,
)


# --------------------------------------------------------------------------- #
# Work types
# --------------------------------------------------------------------------- #
class WorkTypeCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: WorkTypeCategory
    description: str | None = None


class WorkTypePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: WorkTypeCategory | None = None
    description: str | None = None


class WorkTypeResponse(BaseModel):
    id: UUID
    code: str
    name: str
    category: WorkTypeCategory
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, w: WorkType) -> WorkTypeResponse:
        return cls(
            id=w.id,
            code=w.code,
            name=w.name,
            category=w.category,
            description=w.description,
            is_active=w.is_active,
            created_at=w.created_at,
            updated_at=w.updated_at,
        )


# --------------------------------------------------------------------------- #
# Aliases
# --------------------------------------------------------------------------- #
class AliasCreateRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=255)
    kind: AliasKind


class AliasResponse(BaseModel):
    id: UUID
    work_type_id: UUID
    alias: str
    #: The canonical form. Unique across the whole taxonomy, so a collision here
    #: is refused rather than resolved at match time.
    normalised: str
    kind: AliasKind

    @classmethod
    def from_entity(cls, a: WorkTypeAlias) -> AliasResponse:
        return cls(
            id=a.id,
            work_type_id=a.work_type_id,
            alias=a.alias,
            normalised=a.normalised,
            kind=a.kind,
        )


# --------------------------------------------------------------------------- #
# Project tags
# --------------------------------------------------------------------------- #
class ProjectTagRequest(BaseModel):
    work_type_id: UUID
    source: WorkTypeLinkSource = WorkTypeLinkSource.MANUAL
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    #: The description substring justifying the tag, so a reviewer can see the
    #: evidence without re-reading the source document.
    evidence: str | None = None


class ProjectTagResponse(BaseModel):
    project_id: UUID
    work_type_id: UUID
    source: WorkTypeLinkSource
    confidence: Decimal | None
    evidence: str | None

    @classmethod
    def from_entity(cls, t: PastProjectWorkType) -> ProjectTagResponse:
        return cls(
            project_id=t.project_id,
            work_type_id=t.work_type_id,
            source=t.source,
            confidence=t.confidence,
            evidence=t.evidence,
        )


# --------------------------------------------------------------------------- #
# Certified turnover
# --------------------------------------------------------------------------- #
class TurnoverCreateRequest(BaseModel):
    #: Indian financial year, e.g. ``2025-26``. Validated in the service so a
    #: rejection reads as a domain rule rather than a schema quirk.
    financial_year: str = Field(min_length=7, max_length=9)
    contractual_turnover: Decimal = Field(ge=0)
    certificate_document_id: UUID | None = None


class TurnoverPatchRequest(BaseModel):
    contractual_turnover: Decimal | None = Field(default=None, ge=0)
    certificate_document_id: UUID | None = None


class TurnoverResponse(BaseModel):
    id: UUID
    financial_year: str
    contractual_turnover: Decimal
    certificate_document_id: UUID | None
    recorded_by: UUID | None
    recorded_at: datetime

    @classmethod
    def from_entity(cls, t: CompanyTurnover) -> TurnoverResponse:
        return cls(
            id=t.id,
            financial_year=t.financial_year,
            contractual_turnover=t.contractual_turnover,
            certificate_document_id=t.certificate_document_id,
            recorded_by=t.recorded_by,
            recorded_at=t.recorded_at,
        )
