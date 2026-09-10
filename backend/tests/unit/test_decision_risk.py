"""Regression tests locking the risk-engine thresholds (PRD §13.1).

Includes a parametrised boundary case for every relevant C4-table row.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender_intel.domain.decision.models import RiskInput
from tender_intel.domain.decision.risk import RiskEngine
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel

pytestmark = pytest.mark.regression

ENGINE = RiskEngine()


def _assess(*, clause="", emd=None, ev=None, days=None):
    return ENGINE.assess(
        RiskInput(
            estimated_value=Decimal(ev) if ev is not None else None,
            emd_amount=Decimal(emd) if emd is not None else None,
            completion_days=days,
            clause_text=clause,
        )
    )


def _sev(a, cat) -> RiskLevel:
    return a.severity_of(cat)


# --- Performance guarantee (C4: >10 HIGH · 5-10 MEDIUM · <5 LOW) ---
@pytest.mark.parametrize(
    ("pct", "expected"),
    [(11, RiskLevel.HIGH), (10, RiskLevel.MEDIUM), (5, RiskLevel.MEDIUM), (4, RiskLevel.LOW)],
)
def test_performance_guarantee_bands(pct, expected):
    a = _assess(clause=f"a performance guarantee of {pct}% of the contract value is required")
    assert _sev(a, RiskCategory.PERFORMANCE_GUARANTEE) is expected


def test_performance_guarantee_unparseable_is_medium():
    a = _assess(clause="a performance guarantee is required")
    assert _sev(a, RiskCategory.PERFORMANCE_GUARANTEE) is RiskLevel.MEDIUM


def test_performance_guarantee_absent_is_none():
    assert (
        _sev(_assess(clause="ordinary text"), RiskCategory.PERFORMANCE_GUARANTEE) is RiskLevel.NONE
    )


# --- Liquidated damages (same bands) ---
@pytest.mark.parametrize(
    ("pct", "expected"),
    [(11, RiskLevel.HIGH), (10, RiskLevel.MEDIUM), (5, RiskLevel.MEDIUM), (4, RiskLevel.LOW)],
)
def test_liquidated_damages_bands(pct, expected):
    a = _assess(clause=f"liquidated damages up to a maximum of {pct}%")
    assert _sev(a, RiskCategory.LIQUIDATED_DAMAGES) is expected


def test_liquidated_damages_unparseable_is_medium():
    assert _sev(_assess(clause="liquidated damages apply"), RiskCategory.LIQUIDATED_DAMAGES) is (
        RiskLevel.MEDIUM
    )


# --- OEM dependency (MEDIUM if present, else NONE) ---
def test_oem_dependency():
    assert _sev(_assess(clause="OEM authorisation required"), RiskCategory.OEM_DEPENDENCY) is (
        RiskLevel.MEDIUM
    )
    assert (
        _sev(_assess(clause="no such requirement"), RiskCategory.OEM_DEPENDENCY) is RiskLevel.NONE
    )


# --- Short completion (C4: <90 AND >50 lakh HIGH; else <180 MEDIUM; 90/180 edges) ---
@pytest.mark.parametrize(
    ("days", "ev", "clause", "expected"),
    [
        (89, "6000000", "", RiskLevel.HIGH),  # <90 AND value > 50 lakh
        (89, "5000000", "", RiskLevel.MEDIUM),  # value == 50 lakh -> AND fails -> <180
        (90, "10000000", "", RiskLevel.MEDIUM),  # 90 is not < 90
        (179, "10000000", "", RiskLevel.MEDIUM),
        (180, "10000000", "", RiskLevel.NONE),  # 180 not < 180, no urgency
        (180, "10000000", "urgent", RiskLevel.LOW),  # urgency + standard timeline
    ],
)
def test_short_completion(days, ev, clause, expected):
    assert _sev(_assess(days=days, ev=ev, clause=clause), RiskCategory.SHORT_COMPLETION_TIME) is (
        expected
    )


def test_short_completion_unparseable_with_urgency_is_medium():
    a = _assess(days=None, clause="this is urgent work")
    assert _sev(a, RiskCategory.SHORT_COMPLETION_TIME) is RiskLevel.MEDIUM


# --- High EMD (C4: >5 HIGH · 2-5 MEDIUM · <2 or unparseable LOW; absent NONE) ---
@pytest.mark.parametrize(
    ("emd", "expected"),
    [("6", RiskLevel.HIGH), ("5", RiskLevel.MEDIUM), ("2", RiskLevel.MEDIUM), ("1", RiskLevel.LOW)],
)
def test_high_emd_bands(emd, expected):
    assert _sev(_assess(emd=emd, ev="100"), RiskCategory.HIGH_EMD) is expected


def test_high_emd_clause_present_unparseable_is_low():
    assert _sev(_assess(clause="an EMD is required"), RiskCategory.HIGH_EMD) is RiskLevel.LOW


def test_high_emd_absent_is_none():
    assert _sev(_assess(clause="no deposit"), RiskCategory.HIGH_EMD) is RiskLevel.NONE


# --- Special clauses ---
@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("joint venture not allowed", RiskLevel.HIGH),
        ("at the sole discretion of the authority", RiskLevel.HIGH),
        ("disputes settled by arbitration", RiskLevel.MEDIUM),
        ("standard commercial terms", RiskLevel.NONE),
    ],
)
def test_special_clauses(clause, expected):
    assert _sev(_assess(clause=clause), RiskCategory.SPECIAL_CLAUSES) is expected


# --- Severity scores, aggregation (C1 = max) and mitigations ---
def test_severity_scores_are_prd_values():
    a = _assess(clause="joint venture not allowed")  # SPECIAL = HIGH
    special = next(c for c in a.categories if c.category is RiskCategory.SPECIAL_CLAUSES)
    assert special.score == Decimal("8.5")


def test_overall_is_max_and_names_the_dominant_category():
    a = _assess(clause="joint venture not allowed", emd="1", ev="100")  # SPECIAL HIGH, EMD LOW
    assert a.overall_score == Decimal("8.5")
    assert a.overall_severity is RiskLevel.HIGH
    assert a.overall_category is RiskCategory.SPECIAL_CLAUSES


def test_overall_none_when_all_clear():
    a = _assess(clause="ordinary work, standard terms")  # no EMD clause either
    assert a.overall_severity is RiskLevel.NONE
    assert a.overall_score == Decimal("0.0")
    assert a.overall_category is None


def test_mitigations_present_only_when_elevated():
    a = _assess(clause="performance guarantee of 12%")  # PG HIGH
    for c in a.categories:
        if c.severity in (RiskLevel.MEDIUM, RiskLevel.HIGH):
            assert c.mitigations
        else:
            assert c.mitigations == []
