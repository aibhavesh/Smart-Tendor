"""Pure input and result value objects for the decision engines (PRD §13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from tender_intel.domain.enums.eligibility import EligibilityStatus
from tender_intel.domain.enums.recommendation import RecommendationVerdict
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class CompanyFinancials:
    #: The certified three-year average the eligibility screen computed. Net
    #: worth is not held here: FR-303 is retired and nothing reads it.
    turnover: Decimal | None = None


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
    #: Tri-state. ``None`` means the rule could not be evaluated, which is
    #: different from failing it — that difference is what routes a tender to
    #: REVIEW under §13.3 rule 1b instead of NO_BID under rule 1.
    passed: bool | None
    detail: str
    required: Decimal | None = None
    actual: Decimal | None = None
    qualifying_project_id: UUID | None = None
    qualifying_project_name: str | None = None


@dataclass(frozen=True, slots=True)
class QualificationResult:
    #: The eligibility screen's verdict, carried through so §13.3 can tell an
    #: undecidable tender from a failing one.
    status: EligibilityStatus
    rules: list[QualificationRuleResult]

    @property
    def qualified(self) -> bool:
        return self.status is EligibilityStatus.ELIGIBLE

    @property
    def indeterminate(self) -> bool:
        return self.status is EligibilityStatus.INDETERMINATE

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
