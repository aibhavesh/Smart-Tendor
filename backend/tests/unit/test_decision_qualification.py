"""Regression tests locking the qualification-engine rules (PRD §13.2)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from tender_intel.domain.decision.models import (
    CompanyFinancials,
    QualificationInput,
    SimilarWork,
)
from tender_intel.domain.decision.qualification import QualificationEngine

pytestmark = pytest.mark.regression

EV = Decimal("1000")
ENGINE = QualificationEngine()


def _work(value: str) -> SimilarWork:
    return SimilarWork(project_id=uuid4(), name=f"W-{value}", value=Decimal(value))


def _input(
    works,
    *,
    turnover="1500",
    net_worth="1",
    required_work_value=None,
    pct="80",
    net_worth_pct=None,
) -> QualificationInput:
    return QualificationInput(
        estimated_value=EV,
        similar_works=works,
        financials=CompanyFinancials(
            turnover=Decimal(turnover) if turnover is not None else None,
            net_worth=Decimal(net_worth) if net_worth is not None else None,
        ),
        required_work_value=Decimal(required_work_value) if required_work_value else None,
        work_value_required_pct=Decimal(pct) if pct else None,
        net_worth_required_pct=Decimal(net_worth_pct) if net_worth_pct else None,
    )


def _rule(result, name):
    return next(r for r in result.rules if r.name == name)


# --- Work value: single highest project vs configurable % (FR-301) ---
def test_single_work_meets_percentage():
    r = _rule(ENGINE.evaluate(_input([_work("800")])), "work_value")  # 80% of 1000
    assert r.passed
    assert r.qualifying_project_name == "W-800"


def test_single_work_below_percentage_fails():
    assert not _rule(ENGINE.evaluate(_input([_work("799")])), "work_value").passed


def test_two_half_value_works_do_not_qualify():
    # The old 2x50% / 3x40% tiers are gone (FR-301 is a single-project rule).
    r = _rule(ENGINE.evaluate(_input([_work("500"), _work("500")])), "work_value")
    assert not r.passed


def test_parsed_requirement_wins_over_percentage():
    # FR-232: a parsed absolute requirement overrides the % fallback.
    r = _rule(ENGINE.evaluate(_input([_work("500")], required_work_value="500")), "work_value")
    assert r.passed  # 500 >= parsed 500, even though 80% of 1000 = 800


def test_no_required_value_determinable_fails():
    data = QualificationInput(
        estimated_value=None,
        similar_works=[_work("999")],
        financials=CompanyFinancials(),
        required_work_value=None,
        work_value_required_pct=None,
    )
    assert not _rule(ENGINE.evaluate(data), "work_value").passed


# --- Turnover (>= 150% of value) ---
@pytest.mark.parametrize(
    ("turnover", "passes"),
    [("1500", True), ("2000", True), ("1499.99", False), (None, False)],
)
def test_turnover_threshold(turnover, passes):
    assert (
        _rule(
            ENGINE.evaluate(_input([_work("800")], turnover=turnover)), "average_annual_turnover"
        ).passed
        is passes
    )


# --- Net worth: non-negative by default (C3), optional % ---
@pytest.mark.parametrize(
    ("net_worth", "passes"),
    [("1", True), ("0", True), ("-0.01", False), (None, False)],  # 0 PASSES (non-negative)
)
def test_net_worth_non_negative(net_worth, passes):
    assert (
        _rule(ENGINE.evaluate(_input([_work("800")], net_worth=net_worth)), "net_worth").passed
        is passes
    )


def test_net_worth_required_percentage():
    # 30% of 1000 = 300.
    assert _rule(
        ENGINE.evaluate(_input([_work("800")], net_worth="300", net_worth_pct="30")), "net_worth"
    ).passed
    assert not _rule(
        ENGINE.evaluate(_input([_work("800")], net_worth="299", net_worth_pct="30")), "net_worth"
    ).passed


def test_qualified_requires_all_three():
    assert ENGINE.evaluate(_input([_work("800")])).qualified
    assert not ENGINE.evaluate(_input([_work("800")], turnover="10")).qualified
    assert not ENGINE.evaluate(_input([_work("10")])).qualified
