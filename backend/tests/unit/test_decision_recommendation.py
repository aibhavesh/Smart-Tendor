"""Regression tests locking the recommendation engine (PRD §13.3-13.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender_intel.domain.decision.models import (
    CompanyFinancials,
    FieldSignal,
    QualificationResult,
    QualificationRuleResult,
    RecommendationContext,
    RiskAssessment,
    RiskCategoryResult,
)
from tender_intel.domain.decision.recommendation import RecommendationEngine
from tender_intel.domain.enums.recommendation import RecommendationVerdict
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel

pytestmark = pytest.mark.regression

ENGINE = RecommendationEngine()


def _qual(qualified: bool) -> QualificationResult:
    rules = [
        QualificationRuleResult("work_value", qualified, "work ok", qualifying_project_name="P"),
        QualificationRuleResult("average_annual_turnover", qualified, "turnover ok"),
        QualificationRuleResult("net_worth", qualified, "net worth ok"),
    ]
    return QualificationResult(qualified=qualified, rules=rules)


def _risk(score: str) -> RiskAssessment:
    s = Decimal(score)
    if s >= Decimal("8.5"):
        sev = RiskLevel.HIGH
    elif s >= Decimal("5"):
        sev = RiskLevel.MEDIUM
    elif s > 0:
        sev = RiskLevel.LOW
    else:
        sev = RiskLevel.NONE
    cats = [RiskCategoryResult(RiskCategory.HIGH_EMD, sev, s, ["e"])]
    return RiskAssessment(
        categories=cats,
        overall_severity=sev,
        overall_score=s,
        overall_category=RiskCategory.HIGH_EMD if s > 0 else None,
    )


def _sig(known: bool = True, conf: str = "1.0") -> FieldSignal:
    return FieldSignal(known=known, confidence=Decimal(conf))


def _ctx(
    *,
    sim: str | None = None,
    eligibility: bool = False,
    ev: str | None = "100",
    turnover: str | None = None,
    net_worth: str | None = None,
    completion: FieldSignal | None = None,
    emd: FieldSignal | None = None,
    value: FieldSignal | None = None,
) -> RecommendationContext:
    return RecommendationContext(
        estimated_value=Decimal(ev) if ev else None,
        financials=CompanyFinancials(
            turnover=Decimal(turnover) if turnover else None,
            net_worth=Decimal(net_worth) if net_worth else None,
        ),
        best_match_similarity=Decimal(sim) if sim is not None else None,
        eligibility_rules_supplied=eligibility,
        completion_period=completion or _sig(),
        emd=emd or _sig(),
        tender_value=value or _sig(),
    )


def _verdict(qual, risk, ctx):
    return ENGINE.recommend(qual, risk, ctx).verdict


# --- §13.3 ordered rules (first match wins) ---
def test_rule1_qualification_fail_beats_strong_match():
    # Satisfies both rule 1 (fails) and rule 3 (sim > 0.85) -> must be NO_BID.
    v = _verdict(_qual(False), _risk("0"), _ctx(sim="0.90", eligibility=True))
    assert v is RecommendationVerdict.NO_BID


def test_rule2_risk_over_8_is_review():
    assert _verdict(_qual(True), _risk("8.5"), _ctx(sim="0.90")) is RecommendationVerdict.REVIEW


def test_rule2_boundary_8_0_does_not_trigger_review():
    # 8.0 is not > 8.0; no eligibility rules -> rule 4c GO.
    assert _verdict(_qual(True), _risk("8.0"), _ctx(sim=None)) is RecommendationVerdict.GO


def test_rule3_strong_match_go():
    assert _verdict(_qual(True), _risk("0"), _ctx(sim="0.86", eligibility=True)) is (
        RecommendationVerdict.GO
    )


def test_rule3_boundary_0_85_falls_to_review():
    assert _verdict(_qual(True), _risk("0"), _ctx(sim="0.85", eligibility=True)) is (
        RecommendationVerdict.REVIEW
    )


def test_rule4a_boundary_0_40_is_review():
    assert _verdict(_qual(True), _risk("0"), _ctx(sim="0.40", eligibility=True)) is (
        RecommendationVerdict.REVIEW
    )


def test_rule4b_weak_match_no_bid():
    assert _verdict(_qual(True), _risk("0"), _ctx(sim="0.39", eligibility=True)) is (
        RecommendationVerdict.NO_BID
    )


def test_rule4c_no_eligibility_rules_go():
    assert _verdict(_qual(True), _risk("0"), _ctx(sim="0.50", eligibility=False)) is (
        RecommendationVerdict.GO
    )


# --- §13.4 win probability ---
def _win(qual, risk, ctx) -> Decimal:
    return ENGINE.recommend(qual, risk, ctx).win_probability


def test_no_bid_win_probability_is_zero():
    assert _win(_qual(False), _risk("0"), _ctx(sim="0.9", eligibility=True)) == Decimal("0")


@pytest.mark.parametrize(
    ("sim", "expected"),
    [
        ("0.80", "85.0"),  # base 70 + strong 15
        ("0.50", "50.0"),  # base 70 - weak 20
        ("0.65", "67.5"),  # C2 linear: 70 + (-20 + 0.10*175)
        ("0.55", "50.0"),  # anchor
        ("0.75", "85.0"),  # anchor
    ],
)
def test_win_probability_match_curve(sim, expected):
    assert _win(_qual(True), _risk("0"), _ctx(sim=sim)) == Decimal(expected)


def test_win_probability_risk_penalty():
    # base 70 + strong 15 - (2.0 * 3.0) = 79.0
    assert _win(_qual(True), _risk("2.0"), _ctx(sim="0.80")) == Decimal("79.0")


def test_win_probability_financial_bonuses():
    # base 70 + turnover buffer 10 (301 > 3x100) + net-worth 5 (31 > 30% of 100) = 85.0
    ctx = _ctx(sim=None, ev="100", turnover="301", net_worth="31")
    assert _win(_qual(True), _risk("0"), ctx) == Decimal("85.0")


def test_win_probability_clamped_to_95():
    ctx = _ctx(sim="0.80", ev="100", turnover="301", net_worth="31")  # 70+15+10+5 = 100
    assert _win(_qual(True), _risk("0"), ctx) == Decimal("95.0")


def test_win_probability_clamped_to_10():
    # Force below the floor with an (out-of-range) high risk score.
    assert _win(_qual(True), _risk("20"), _ctx(sim="0.50")) == Decimal("10.0")


# --- §13.5 confidence ---
def _conf(ctx) -> Decimal:
    return ENGINE.recommend(_qual(True), _risk("0"), ctx).confidence


def test_confidence_full_data():
    assert _conf(
        _ctx(completion=_sig(True, "0.9"), emd=_sig(True, "0.9"), value=_sig(True, "0.9"))
    ) == Decimal("0.9")


def test_confidence_missing_field_penalty_and_cap():
    # completion missing (conf 0): score 1.0-0.1=0.9; cap (0+0.9+0.9)/3=0.6 -> 0.6
    ctx = _ctx(completion=_sig(False, "0"), emd=_sig(True, "0.9"), value=_sig(True, "0.9"))
    assert _conf(ctx) == Decimal("0.6")


def test_confidence_capped_by_extraction_confidence():
    # All present but low-confidence: score 1.0 capped by mean 0.3 -> 0.3 (§13.5 cap).
    ctx = _ctx(completion=_sig(True, "0.3"), emd=_sig(True, "0.3"), value=_sig(True, "0.3"))
    assert _conf(ctx) == Decimal("0.3")


def test_confidence_floor():
    ctx = _ctx(completion=_sig(False, "0"), emd=_sig(False, "0"), value=_sig(False, "0"))
    assert _conf(ctx) == Decimal("0.1")


# --- Pros / cons / checklist ---
def test_pros_cons_and_checklist():
    cats = [
        RiskCategoryResult(
            RiskCategory.PERFORMANCE_GUARANTEE, RiskLevel.HIGH, Decimal("8.5"), ["PG 12%"]
        )
    ]
    risk = RiskAssessment(cats, RiskLevel.HIGH, Decimal("8.5"), RiskCategory.PERFORMANCE_GUARANTEE)
    rec = ENGINE.recommend(_qual(True), risk, _ctx(sim="0.9"))
    assert any("via 'P'" in p for p in rec.pros)
    assert any("PERFORMANCE_GUARANTEE" in c for c in rec.cons)
    assert "Tender fee payment receipt" in rec.document_checklist
    assert "Completion certificates for the qualifying similar works" in rec.document_checklist
    assert "Arrange the performance guarantee (bank guarantee)" in rec.document_checklist
    assert len(rec.document_checklist) == len(set(rec.document_checklist))
