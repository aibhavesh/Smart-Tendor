"""Pure input and result value objects for the decision engines (PRD §13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from tender_intel.domain.enums.recommendation import RecommendationVerdict
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CompanyFinancials:
    turnover: Decimal | None = None  # average annual turnover
    net_worth: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SimilarWork:
    project_id: UUID
    name: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class QualificationInput:
    estimated_value: Decimal | None
    similar_works: list[SimilarWork]
    financials: CompanyFinancials
    # FR-232 parses the tender's own stated required value; when present it wins
    # over the configurable percentage fallback (D1).
    required_work_value: Decimal | None = None
    work_value_required_pct: Decimal | None = None  # fallback %, e.g. Decimal("80")
    net_worth_required_pct: Decimal | None = None  # optional (FR-303 / D2)


@dataclass(frozen=True, slots=True)
class RiskInput:
    estimated_value: Decimal | None
    emd_amount: Decimal | None
    completion_days: int | None
    clause_text: str


@dataclass(frozen=True, slots=True)
class FieldSignal:
    """Presence + extraction confidence of one metadata field (for §13.5)."""

    known: bool
    confidence: Decimal


@dataclass(frozen=True, slots=True)
class RecommendationContext:
    estimated_value: Decimal | None
    financials: CompanyFinancials
    best_match_similarity: Decimal | None
    eligibility_rules_supplied: bool
    # The exactly-three fields §13.5 scores confidence against.
    completion_period: FieldSignal
    emd: FieldSignal
    tender_value: FieldSignal


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class QualificationRuleResult:
    name: str
    passed: bool
    detail: str
    required: Decimal | None = None
    actual: Decimal | None = None
    qualifying_project_id: UUID | None = None
    qualifying_project_name: str | None = None


@dataclass(frozen=True, slots=True)
class QualificationResult:
    qualified: bool
    rules: list[QualificationRuleResult]

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.rules if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.rules if not r.passed)


@dataclass(frozen=True, slots=True)
class RiskCategoryResult:
    category: RiskCategory
    severity: RiskLevel
    score: Decimal  # 0..10 (FR-312)
    evidence: list[str]
    mitigations: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    categories: list[RiskCategoryResult]
    overall_severity: RiskLevel
    overall_score: Decimal  # 0..10, aggregated by max (C1)
    overall_category: RiskCategory | None  # category of the highest finding (FR-316)

    def severity_of(self, category: RiskCategory) -> RiskLevel:
        for result in self.categories:
            if result.category is category:
                return result.severity
        return RiskLevel.NONE


@dataclass(frozen=True, slots=True)
class Recommendation:
    verdict: RecommendationVerdict
    win_probability: Decimal  # percentage points, 10..95 (0 for NO_BID)
    confidence: Decimal  # 0.0..1.0
    pros: list[str]
    cons: list[str]
    document_checklist: list[str]
    applied_rules: list[str]
