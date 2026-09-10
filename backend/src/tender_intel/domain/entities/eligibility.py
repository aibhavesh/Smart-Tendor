"""TenderEligibility — the stored screening annotation (feature spec §7).

One row per tender, replaced on every re-evaluation. It is an annotation and not
a lifecycle state: a NOT_ELIGIBLE tender is not deleted or auto-rejected, it
simply does not advance to a recommendation.

The row stores the fingerprint of the inputs it was computed from. Staleness is
derived by recomputing that digest and comparing, so no flag has to be flipped by
whoever changed the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from tender_intel.domain.decision.eligibility import (
    EligibilityResult,
    EligibilityRuleResult,
    QualifyingProject,
    WorkTypeMatch,
)
from tender_intel.domain.enums.eligibility import EligibilityStatus, SimilarWorkRule


def _now() -> datetime:
    return datetime.now(UTC)


def _combine(*rules: EligibilityRuleResult) -> bool | None:
    """Tri-state AND: a definite failure wins, then an unknown, else True."""
    if any(r.passed is False for r in rules):
        return False
    if any(r.passed is None for r in rules):
        return None
    return True


@dataclass(slots=True)
class TenderEligibility:
    tender_id: UUID
    status: EligibilityStatus
    inputs_fingerprint: str
    financial_pass: bool | None = None
    financial_required: Decimal | None = None
    financial_actual: Decimal | None = None
    technical_pass: bool | None = None
    rule_satisfied: SimilarWorkRule | None = None
    reasons: list[str] = field(default_factory=list)
    matched_work_types: list[WorkTypeMatch] = field(default_factory=list)
    qualifying_projects: list[QualifyingProject] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=_now)

    @classmethod
    def from_result(
        cls, tender_id: UUID, result: EligibilityResult, *, fingerprint: str
    ) -> TenderEligibility:
        return cls(
            tender_id=tender_id,
            status=result.status,
            inputs_fingerprint=fingerprint,
            financial_pass=result.financial.passed,
            financial_required=result.financial.required,
            financial_actual=result.financial.actual,
            technical_pass=_combine(result.technical_match, result.technical_value),
            rule_satisfied=result.rule_satisfied,
            reasons=list(result.reasons),
            matched_work_types=list(result.matched_work_types),
            qualifying_projects=list(result.qualifying_projects),
        )

    @property
    def is_eligible(self) -> bool:
        return self.status is EligibilityStatus.ELIGIBLE

    def snapshot(self) -> dict[str, Any]:
        """Compact form for an audit diff."""
        return {
            "status": self.status.value,
            "financial_pass": self.financial_pass,
            "technical_pass": self.technical_pass,
            "rule_satisfied": self.rule_satisfied.value if self.rule_satisfied else None,
        }


@dataclass(slots=True)
class EligibilityNotification:
    """One digest send, recorded so a tender is not notified twice.

    Keyed on the eligibility result's ``inputs_fingerprint`` rather than the
    tender alone. Re-screening unchanged inputs is silent; a result that
    genuinely changed notifies again, because the second result is news.

    ``recipients`` holds the addresses actually resolved at send time. The set
    moves as roles change, so it is recorded rather than recomputed later.
    """

    tender_id: UUID
    inputs_fingerprint: str
    status: EligibilityStatus
    recipients: list[str] = field(default_factory=list)
    sent_at: datetime = field(default_factory=_now)
    id: UUID = field(default_factory=uuid4)
