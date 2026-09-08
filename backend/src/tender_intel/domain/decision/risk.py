"""Risk engine (PRD §13.1) — six FR-311 categories, 0-10 scale, max aggregation.

Each category yields a severity (NONE..HIGH) with evidence and, when elevated,
a mitigation. The overall score/category is the highest-scoring finding (C1).
"""

from __future__ import annotations

from decimal import Decimal

from tender_intel.domain.decision import thresholds as th
from tender_intel.domain.decision.clause_scan import contains_any, scan_percent_clause
from tender_intel.domain.decision.models import (
    RiskAssessment,
    RiskCategoryResult,
    RiskInput,
)
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel

_MITIGATIONS: dict[RiskCategory, str] = {
    RiskCategory.PERFORMANCE_GUARANTEE: "Confirm cash-flow cover for the performance guarantee.",
    RiskCategory.LIQUIDATED_DAMAGES: "Price the liquidated-damages exposure into the bid.",
    RiskCategory.OEM_DEPENDENCY: "Secure the OEM authorisation / MAF before bidding.",
    RiskCategory.SHORT_COMPLETION_TIME: "Validate the schedule and resource plan for the timeline.",
    RiskCategory.HIGH_EMD: "Confirm funds to block the EMD without straining cash flow.",
    RiskCategory.SPECIAL_CLAUSES: "Have legal review the restrictive / discretionary clauses.",
}


class RiskEngine:
    def assess(self, data: RiskInput) -> RiskAssessment:
        categories = [
            self._performance_guarantee(data),
            self._liquidated_damages(data),
            self._oem_dependency(data),
            self._short_completion(data),
            self._high_emd(data),
            self._special_clauses(data),
        ]
        # C1: aggregate by max — a single HIGH finding drives the overall score.
        top = max(categories, key=lambda c: c.score)
        if top.score == th.RISK_NONE_SCORE:
            return RiskAssessment(categories, RiskLevel.NONE, th.RISK_NONE_SCORE, None)
        return RiskAssessment(categories, top.severity, top.score, top.category)

    # ------------------------------------------------------------------ #
    def _performance_guarantee(self, data: RiskInput) -> RiskCategoryResult:
        cat = RiskCategory.PERFORMANCE_GUARANTEE
        hit = scan_percent_clause(data.clause_text, th.PERFORMANCE_GUARANTEE_KEYWORDS)
        if not hit.present:
            return self._result(cat, RiskLevel.NONE, ["No performance-guarantee clause detected."])
        return self._percent_banded(cat, hit.percent, "Performance guarantee")

    def _liquidated_damages(self, data: RiskInput) -> RiskCategoryResult:
        cat = RiskCategory.LIQUIDATED_DAMAGES
        hit = scan_percent_clause(data.clause_text, th.LIQUIDATED_DAMAGES_KEYWORDS)
        if not hit.present:
            return self._result(cat, RiskLevel.NONE, ["No liquidated-damages clause detected."])
        return self._percent_banded(cat, hit.percent, "Liquidated-damages cap")

    def _oem_dependency(self, data: RiskInput) -> RiskCategoryResult:
        cat = RiskCategory.OEM_DEPENDENCY
        if contains_any(data.clause_text, th.OEM_DEPENDENCY_KEYWORDS):
            return self._result(
                cat, RiskLevel.MEDIUM, ["OEM authorisation / MAF requirement detected."]
            )
        return self._result(cat, RiskLevel.NONE, ["No OEM dependency detected."])

    def _short_completion(self, data: RiskInput) -> RiskCategoryResult:
        cat = RiskCategory.SHORT_COMPLETION_TIME
        urgency = contains_any(data.clause_text, th.SHORT_COMPLETION_URGENCY_KEYWORDS)
        days = data.completion_days
        if days is None:
            # FR-315: urgency wording but no parseable timeline -> MEDIUM.
            if urgency:
                return self._result(
                    cat, th.FR315_UNPARSEABLE_SEVERITY, ["Urgency wording; timeline unparseable."]
                )
            return self._result(cat, RiskLevel.NONE, ["No completion-time concern detected."])
        ev = data.estimated_value
        if (
            days < th.COMPLETION_HIGH_MAX_DAYS_EXCLUSIVE
            and ev is not None
            and ev > th.COMPLETION_HIGH_VALUE_MIN_EXCLUSIVE
        ):
            return self._result(cat, RiskLevel.HIGH, [f"{days} days on a tender above 50 lakh."])
        if days < th.COMPLETION_MEDIUM_MAX_DAYS_EXCLUSIVE:
            return self._result(cat, RiskLevel.MEDIUM, [f"Completion period is {days} days."])
        if urgency:
            return self._result(
                cat, RiskLevel.LOW, [f"Urgency wording; timeline {days} days is standard."]
            )
        return self._result(cat, RiskLevel.NONE, [f"Completion period is {days} days."])

    def _high_emd(self, data: RiskInput) -> RiskCategoryResult:
        cat = RiskCategory.HIGH_EMD
        ev, emd = data.estimated_value, data.emd_amount
        if emd is not None and ev is not None and ev > 0:
            pct = emd / ev * Decimal("100")
            if pct > th.EMD_HIGH_MIN_EXCLUSIVE:
                severity = RiskLevel.HIGH
            elif pct >= th.EMD_MEDIUM_MIN_INCLUSIVE:
                severity = RiskLevel.MEDIUM
            else:
                severity = RiskLevel.LOW
            return self._result(cat, severity, [f"EMD is {pct:.2f}% of the tender value."])
        if contains_any(data.clause_text, th.HIGH_EMD_KEYWORDS):
            # Per §13.1: EMD clause present without parseable values -> LOW.
            return self._result(
                cat, th.EMD_UNPARSEABLE_SEVERITY, ["EMD present but not quantifiable."]
            )
        return self._result(cat, RiskLevel.NONE, ["No EMD requirement detected."])

    def _special_clauses(self, data: RiskInput) -> RiskCategoryResult:
        cat = RiskCategory.SPECIAL_CLAUSES
        if contains_any(data.clause_text, th.SPECIAL_CLAUSE_JV_BARRED_KEYWORDS):
            return self._result(cat, RiskLevel.HIGH, ["Joint venture / consortium barred."])
        if contains_any(data.clause_text, th.SPECIAL_CLAUSE_SOLE_DISCRETION_KEYWORDS):
            return self._result(cat, RiskLevel.HIGH, ["Sole-discretion clause detected."])
        if contains_any(data.clause_text, th.SPECIAL_CLAUSE_ARBITRATION_KEYWORDS):
            return self._result(cat, RiskLevel.MEDIUM, ["Arbitration / dispute-resolution clause."])
        return self._result(cat, RiskLevel.NONE, ["No restrictive special clauses detected."])

    # ------------------------------------------------------------------ #
    def _percent_banded(
        self, category: RiskCategory, percent: Decimal | None, label: str
    ) -> RiskCategoryResult:
        if percent is None:
            # FR-315: keyword present, magnitude unparseable -> MEDIUM.
            return self._result(
                category, th.FR315_UNPARSEABLE_SEVERITY, [f"{label} present; % unparseable."]
            )
        if percent > th.PCT_HIGH_MIN_EXCLUSIVE:
            severity = RiskLevel.HIGH
        elif percent >= th.PCT_MEDIUM_MIN_INCLUSIVE:
            severity = RiskLevel.MEDIUM
        else:
            severity = RiskLevel.LOW
        return self._result(category, severity, [f"{label} is {percent}% of the tender value."])

    @staticmethod
    def _result(
        category: RiskCategory, severity: RiskLevel, evidence: list[str]
    ) -> RiskCategoryResult:
        mitigations = (
            [_MITIGATIONS[category]] if severity in (RiskLevel.MEDIUM, RiskLevel.HIGH) else []
        )
        return RiskCategoryResult(
            category=category,
            severity=severity,
            score=th.SEVERITY_SCORES[severity],
            evidence=evidence,
            mitigations=mitigations,
        )
