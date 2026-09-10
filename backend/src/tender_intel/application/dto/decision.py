"""Decision result DTO (combined engine output)."""

from __future__ import annotations

from dataclasses import dataclass

from tender_intel.domain.decision.models import (
    QualificationResult,
    Recommendation,
    RiskAssessment,
)


@dataclass(frozen=True, slots=True)
class DecisionResult:
    qualification: QualificationResult
    risk: RiskAssessment
    recommendation: Recommendation
