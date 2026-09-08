"""Recommendation engine (PRD §13.3-13.5) — pure and deterministic.

The GO/REVIEW/NO_BID verdict comes from the §13.3 ordered rules (first match
wins); win probability (§13.4) is driven by match similarity; confidence (§13.5)
by extraction completeness capped by the extraction confidences. The AI Analyst
(Phase 7) narrates this output but never changes it.
"""

from __future__ import annotations

from decimal import Decimal

from tender_intel.domain.decision import thresholds as th
from tender_intel.domain.decision.models import (
    QualificationResult,
    Recommendation,
    RecommendationContext,
    RiskAssessment,
)
from tender_intel.domain.enums.recommendation import RecommendationVerdict
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel

_HUNDRED = Decimal("100")
_WIN_QUANTUM = Decimal("0.1")

_BASE_CHECKLIST = [
    "Tender fee payment receipt",
    "EMD / bid security proof",
    "Company registration certificate",
    "PAN card",
    "GST registration",
]

_RISK_CHECKLIST: dict[RiskCategory, str] = {
    RiskCategory.PERFORMANCE_GUARANTEE: "Arrange the performance guarantee (bank guarantee)",
    RiskCategory.LIQUIDATED_DAMAGES: "Written acceptance of the liquidated-damages clause",
    RiskCategory.OEM_DEPENDENCY: "OEM authorisation letter / MAF",
    RiskCategory.SHORT_COMPLETION_TIME: "Schedule and resource plan for the completion timeline",
    RiskCategory.HIGH_EMD: "EMD instrument (DD / bank guarantee) arrangement",
    RiskCategory.SPECIAL_CLAUSES: "Legal sign-off on the restrictive special clauses",
}

_QUAL_CHECKLIST: dict[str, str] = {
    "work_value": "Completion certificates for the qualifying similar works",
    "average_annual_turnover": "Audited financial statements for the last 3 years",
    "net_worth": "Chartered Accountant net-worth certificate",
}


class RecommendationEngine:
    def recommend(
        self,
        qualification: QualificationResult,
        risk: RiskAssessment,
        context: RecommendationContext,
    ) -> Recommendation:
        verdict, applied = self._verdict(qualification, risk, context)
        return Recommendation(
            verdict=verdict,
            win_probability=self._win_probability(verdict, risk, context),
            confidence=self._confidence(context),
            pros=self._pros(qualification, risk),
            cons=self._cons(qualification, risk),
            document_checklist=self._checklist(qualification, risk),
            applied_rules=applied,
        )

    # ------------------------------------------------------------------ #
    # §13.3 — ordered rules, first match wins
    # ------------------------------------------------------------------ #
    @staticmethod
    def _verdict(
        qualification: QualificationResult,
        risk: RiskAssessment,
        context: RecommendationContext,
    ) -> tuple[RecommendationVerdict, list[str]]:
        sim = context.best_match_similarity

        # Rule 1 — financial qualification fails.
        if not qualification.qualified:
            return RecommendationVerdict.NO_BID, ["rule_1_qualification_fail"]
        # Rule 2 — overall risk score > 8.0.
        if risk.overall_score > th.RISK_REVIEW_SCORE_MIN_EXCLUSIVE:
            return RecommendationVerdict.REVIEW, ["rule_2_risk_over_8"]
        # Rule 3 — strong match and qualification passes.
        if sim is not None and sim > th.SIMILARITY_GO_MIN_EXCLUSIVE:
            return RecommendationVerdict.GO, ["rule_3_strong_match_go"]
        # Rules 4a/4b — eligibility rules supplied: judge by similarity band.
        if context.eligibility_rules_supplied:
            effective = sim if sim is not None else Decimal("0")
            if effective >= th.SIMILARITY_REVIEW_MIN_INCLUSIVE:
                return RecommendationVerdict.REVIEW, ["rule_4a_mid_match_review"]
            return RecommendationVerdict.NO_BID, ["rule_4b_weak_match_no_bid"]
        # Rule 4c — no eligibility rules, qualified, risk acceptable (<= 8.0).
        return RecommendationVerdict.GO, ["rule_4c_qualified_go"]

    # ------------------------------------------------------------------ #
    # §13.4 — win probability
    # ------------------------------------------------------------------ #
    @staticmethod
    def _win_probability(
        verdict: RecommendationVerdict, risk: RiskAssessment, context: RecommendationContext
    ) -> Decimal:
        if verdict is RecommendationVerdict.NO_BID:
            return th.NO_BID_WIN_PROBABILITY

        score = th.WIN_BASE
        sim = context.best_match_similarity
        if sim is not None:
            if sim > th.WIN_STRONG_MATCH_MIN_EXCLUSIVE:
                score += th.WIN_STRONG_MATCH_BONUS
            elif sim < th.WIN_WEAK_MATCH_MAX_EXCLUSIVE:
                score -= th.WIN_WEAK_MATCH_PENALTY
            else:  # C2 — linear interpolation across the intermediate band
                score += (
                    -th.WIN_WEAK_MATCH_PENALTY
                    + (sim - th.WIN_WEAK_MATCH_MAX_EXCLUSIVE) * th.WIN_INTERMEDIATE_SLOPE
                )

        score -= risk.overall_score * th.WIN_RISK_PENALTY_PER_POINT

        ev = context.estimated_value
        turnover = context.financials.turnover
        net_worth = context.financials.net_worth
        if ev is not None and ev > 0:
            if turnover is not None and turnover > th.WIN_TURNOVER_BUFFER_MULTIPLE * ev:
                score += th.WIN_TURNOVER_BUFFER_BONUS
            if (
                net_worth is not None
                and net_worth > th.WIN_NET_WORTH_PCT_MIN_EXCLUSIVE / _HUNDRED * ev
            ):
                score += th.WIN_NET_WORTH_BONUS

        clamped = max(th.WIN_MIN, min(th.WIN_MAX, score))
        return clamped.quantize(_WIN_QUANTUM)

    # ------------------------------------------------------------------ #
    # §13.5 — confidence
    # ------------------------------------------------------------------ #
    @staticmethod
    def _confidence(context: RecommendationContext) -> Decimal:
        fields = (context.completion_period, context.emd, context.tender_value)
        missing = sum(1 for f in fields if not f.known)
        score = th.CONFIDENCE_BASE - th.CONFIDENCE_PENALTY_PER_MISSING_FIELD * missing
        cap = sum((f.confidence for f in fields), Decimal("0")) / Decimal(len(fields))
        bounded = max(th.CONFIDENCE_MIN, min(th.CONFIDENCE_MAX, min(score, cap)))
        return bounded

    # ------------------------------------------------------------------ #
    @staticmethod
    def _pros(qualification: QualificationResult, risk: RiskAssessment) -> list[str]:
        pros: list[str] = []
        for rule in qualification.rules:
            if rule.passed:
                text = rule.detail
                if rule.qualifying_project_name:
                    text += f" (via '{rule.qualifying_project_name}')"
                pros.append(text)
        for category in risk.categories:
            if category.severity in (RiskLevel.NONE, RiskLevel.LOW):
                pros.append(f"{category.category.value} risk is low.")
        return pros

    @staticmethod
    def _cons(qualification: QualificationResult, risk: RiskAssessment) -> list[str]:
        cons: list[str] = []
        for rule in qualification.rules:
            if not rule.passed:
                cons.append(rule.detail)
        for category in risk.categories:
            if category.severity in (RiskLevel.MEDIUM, RiskLevel.HIGH):
                evidence = category.evidence[0] if category.evidence else ""
                cons.append(f"{category.severity.value} {category.category.value} risk: {evidence}")
        return cons

    @staticmethod
    def _checklist(qualification: QualificationResult, risk: RiskAssessment) -> list[str]:
        checklist = list(_BASE_CHECKLIST)
        for rule in qualification.rules:
            if rule.passed and rule.name in _QUAL_CHECKLIST:
                checklist.append(_QUAL_CHECKLIST[rule.name])
        for category in risk.categories:
            if category.severity in (RiskLevel.MEDIUM, RiskLevel.HIGH):
                checklist.append(_RISK_CHECKLIST[category.category])
        return list(dict.fromkeys(checklist))
