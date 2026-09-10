"""Eligibility screening response schemas (feature spec §8)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from tender_intel.domain.entities.eligibility import TenderEligibility
from tender_intel.domain.enums.eligibility import (
    EligibilityStatus,
    MatchGrade,
    MatchMethod,
    SimilarWorkRule,
)


class MatchedWorkTypeResponse(BaseModel):
    work_type_id: UUID
    code: str
    method: MatchMethod
    score: Decimal
    grade: MatchGrade


class QualifyingProjectResponse(BaseModel):
    project_id: UUID
    name: str
    rank: int
    work_value: Decimal


class EligibilityResponse(BaseModel):
    tender_id: UUID
    status: EligibilityStatus
    #: True when the stored result no longer describes the current inputs.
    #: Derived by recomputing the input fingerprint, never stored as a flag.
    is_stale: bool
    financial_pass: bool | None
    financial_required: Decimal | None
    financial_actual: Decimal | None
    technical_pass: bool | None
    rule_satisfied: SimilarWorkRule | None
    #: Every rule that did not pass, in the engine's own words.
    reasons: list[str]
    matched_work_types: list[MatchedWorkTypeResponse]
    qualifying_projects: list[QualifyingProjectResponse]
    evaluated_at: datetime

    @classmethod
    def from_entity(cls, e: TenderEligibility, *, is_stale: bool) -> EligibilityResponse:
        return cls(
            tender_id=e.tender_id,
            status=e.status,
            is_stale=is_stale,
            financial_pass=e.financial_pass,
            financial_required=e.financial_required,
            financial_actual=e.financial_actual,
            technical_pass=e.technical_pass,
            rule_satisfied=e.rule_satisfied,
            reasons=list(e.reasons),
            matched_work_types=[
                MatchedWorkTypeResponse(
                    work_type_id=m.work_type_id,
                    code=m.code,
                    method=m.method,
                    score=m.score,
                    grade=m.grade,
                )
                for m in e.matched_work_types
            ],
            qualifying_projects=[
                QualifyingProjectResponse(
                    project_id=q.project_id,
                    name=q.name,
                    rank=q.rank,
                    work_value=q.work_value,
                )
                for q in e.qualifying_projects
            ],
            evaluated_at=e.evaluated_at,
        )
