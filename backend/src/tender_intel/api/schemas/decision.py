"""Decision (qualification + risk + recommendation) response schemas."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from tender_intel.application.dto.decision import DecisionResult
from tender_intel.domain.decision.models import (
    QualificationResult,
    RiskAssessment,
)


def _d(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


class QualificationRuleResponse(BaseModel):
    name: str
    passed: bool
    detail: str
    required: str | None
    actual: str | None
    qualifying_project_id: UUID | None
    qualifying_project_name: str | None


class QualificationResponse(BaseModel):
    qualified: bool
    rules: list[QualificationRuleResponse]

    @classmethod
    def from_result(cls, q: QualificationResult) -> QualificationResponse:
        return cls(
            qualified=q.qualified,
            rules=[
                QualificationRuleResponse(
                    name=r.name,
                    passed=r.passed,
                    detail=r.detail,
                    required=_d(r.required),
                    actual=_d(r.actual),
                    qualifying_project_id=r.qualifying_project_id,
                    qualifying_project_name=r.qualifying_project_name,
                )
                for r in q.rules
            ],
        )


class RiskCategoryResponse(BaseModel):
    category: str
    severity: str
    score: float  # 0..10
    evidence: list[str]
    mitigations: list[str]


class RiskResponse(BaseModel):
    overall_severity: str
    overall_score: float  # 0..10
    overall_category: str | None  # category of the highest finding
    categories: list[RiskCategoryResponse]

    @classmethod
    def from_result(cls, r: RiskAssessment) -> RiskResponse:
        return cls(
            overall_severity=r.overall_severity.value,
            overall_score=float(r.overall_score),
            overall_category=r.overall_category.value if r.overall_category else None,
            categories=[
                RiskCategoryResponse(
                    category=c.category.value,
                    severity=c.severity.value,
                    score=float(c.score),
                    evidence=c.evidence,
                    mitigations=c.mitigations,
                )
                for c in r.categories
            ],
        )


class RecommendationResponse(BaseModel):
    verdict: str
    win_probability: float  # percentage points, 0 for NO_BID
    confidence: float  # 0.0..1.0
    pros: list[str]
    cons: list[str]
    document_checklist: list[str]
    applied_rules: list[str]


class DecisionResponse(BaseModel):
    tender_id: UUID
    qualification: QualificationResponse
    risk: RiskResponse
    recommendation: RecommendationResponse
    #: True when the tender's most recent *recorded verdict* predates a metadata
    #: correction, so the decision on file rests on evidence that has changed.
    #:
    #: This does NOT mean the payload below is stale. Recommendations are never
    #: stored — this one was recomputed from current metadata on this request.
    #: The flag warns that the human decision needs revisiting; it never
    #: suppresses or alters the recommendation.
    verdict_is_stale: bool = False

    @classmethod
    def from_result(
        cls, tender_id: UUID, result: DecisionResult, *, verdict_is_stale: bool = False
    ) -> DecisionResponse:
        rec = result.recommendation
        return cls(
            tender_id=tender_id,
            verdict_is_stale=verdict_is_stale,
            qualification=QualificationResponse.from_result(result.qualification),
            risk=RiskResponse.from_result(result.risk),
            recommendation=RecommendationResponse(
                verdict=rec.verdict.value,
                win_probability=float(rec.win_probability),
                confidence=float(rec.confidence),
                pros=rec.pros,
                cons=rec.cons,
                document_checklist=rec.document_checklist,
                applied_rules=rec.applied_rules,
            ),
        )
