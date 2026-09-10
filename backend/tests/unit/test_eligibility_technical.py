"""Technical criterion — stage B, the 3/2/1 similar-work value test.

Feature spec §3. Marked ``regression``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from tender_intel.domain.decision.eligibility import (
    CandidateProject,
    EligibilityEngine,
    EligibilityInput,
    TurnoverYear,
    WorkTypeMatch,
)
from tender_intel.domain.enums.eligibility import MatchGrade, MatchMethod, SimilarWorkRule
from tender_intel.domain.services.financial_year import FinancialYear

pytestmark = pytest.mark.regression

CRORE = Decimal("10000000")
CLOSING = date(2026, 4, 1)  # window is 2019-20 .. 2025-26
IN_WINDOW = date(2024, 6, 1)
BEFORE_WINDOW = date(2018, 6, 1)

TYPE_A, TYPE_B = uuid4(), uuid4()


def matched(*ids, grade: MatchGrade = MatchGrade.MATCHED) -> list[WorkTypeMatch]:
    return [
        WorkTypeMatch(i, f"CODE_{n}", MatchMethod.EXACT, Decimal("1.0"), grade)
        for n, i in enumerate(ids)
    ]


def project(
    value: str | None,
    *,
    types: tuple = (TYPE_A,),
    cert: date | None = IN_WINDOW,
    name: str = "Project",
) -> CandidateProject:
    return CandidateProject(
        project_id=uuid4(),
        name=name,
        work_value=None if value is None else Decimal(value),
        completion_certificate_date=cert,
        work_type_ids=frozenset(types),
    )


def evaluate(candidates, *, value=CRORE, closing=CLOSING, matches=None):
    return EligibilityEngine().evaluate(
        EligibilityInput(
            tender_value=value,
            completion_years=Decimal("2"),
            closing_date=closing,
            turnover_years=[
                TurnoverYear(FinancialYear(2022 + i), Decimal("999999999")) for i in range(3)
            ],
            matches=matches if matches is not None else matched(TYPE_A),
            candidates=candidates,
        )
    )


# --------------------------------------------------------------------------- #
# The three nested rules
# --------------------------------------------------------------------------- #
def test_one_project_at_sixty_percent_passes():
    result = evaluate([project("6000000")])
    assert result.technical_value.passed is True
    assert result.rule_satisfied is SimilarWorkRule.ONE_AT_60


def test_two_projects_at_forty_percent_pass():
    result = evaluate([project("4500000"), project("4200000")])
    assert result.rule_satisfied is SimilarWorkRule.TWO_AT_40


def test_three_projects_at_thirty_percent_pass():
    result = evaluate([project("3500000"), project("3200000"), project("3100000")])
    assert result.rule_satisfied is SimilarWorkRule.THREE_AT_30


def test_the_strongest_rule_wins_and_is_not_double_counted():
    # A project clearing 60% also clears 40% and 30%. Only 1x60 is reported.
    result = evaluate([project("9000000"), project("8000000"), project("7000000")])
    assert result.rule_satisfied is SimilarWorkRule.ONE_AT_60
    assert len(result.qualifying_projects) == 1


def test_just_below_every_tier_fails():
    result = evaluate([project("2900000"), project("2900000"), project("2900000")])
    assert result.technical_value.passed is False
    assert result.rule_satisfied is None


def test_boundary_at_exactly_sixty_percent_passes():
    result = evaluate([project("6000000")])
    assert result.technical_value.passed is True


def test_one_paisa_below_sixty_still_reaches_a_lower_tier():
    # 5999999.99 misses 1x60 but clears 3x30 on its own? No: 3x30 needs three
    # projects. With one project only, the whole test fails.
    result = evaluate([project("5999999.99")])
    assert result.technical_value.passed is False


# --------------------------------------------------------------------------- #
# The candidate pool
# --------------------------------------------------------------------------- #
def test_projects_pool_across_matched_types():
    result = evaluate(
        [project("4500000", types=(TYPE_A,)), project("4200000", types=(TYPE_B,))],
        matches=matched(TYPE_A, TYPE_B),
    )
    assert result.rule_satisfied is SimilarWorkRule.TWO_AT_40


def test_a_project_carrying_an_unmatched_type_is_excluded():
    result = evaluate([project("9000000", types=(TYPE_B,))], matches=matched(TYPE_A))
    assert result.technical_value.passed is False


def test_a_project_is_counted_once_even_carrying_two_matched_types():
    result = evaluate([project("4500000", types=(TYPE_A, TYPE_B))], matches=matched(TYPE_A, TYPE_B))
    # One project cannot satisfy 2x40 however many types it carries.
    assert result.technical_value.passed is False


# --------------------------------------------------------------------------- #
# The certificate filter
# --------------------------------------------------------------------------- #
def test_a_blank_certificate_date_is_excluded():
    result = evaluate([project("9000000", cert=None)])
    assert result.technical_value.passed is False


def test_a_certificate_outside_the_window_is_excluded():
    result = evaluate([project("9000000", cert=BEFORE_WINDOW)])
    assert result.technical_value.passed is False


def test_the_window_anchors_to_the_closing_date_not_to_today():
    # The same project passes against a later closing date and fails against an
    # earlier one, purely because the seven-year window moves with the anchor.
    old = date(2013, 6, 1)
    assert evaluate([project("9000000", cert=old)], closing=CLOSING).technical_value.passed is False
    assert (
        evaluate([project("9000000", cert=old)], closing=date(2015, 4, 1)).technical_value.passed
        is True
    )


def test_a_project_without_a_value_is_excluded():
    result = evaluate([project(None)])
    assert result.technical_value.passed is False


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def test_qualifying_projects_are_ranked_and_named():
    result = evaluate(
        [project("4500000", name="Alpha"), project("4200000", name="Beta")],
    )
    assert [q.rank for q in result.qualifying_projects] == [1, 2]
    assert [q.name for q in result.qualifying_projects] == ["Alpha", "Beta"]
    assert "Alpha" in result.technical_value.detail


def test_a_failure_names_the_window_and_the_rules():
    result = evaluate([project("100")])
    assert "2019-20" in result.technical_value.detail
    assert "2025-26" in result.technical_value.detail


# --------------------------------------------------------------------------- #
# Indeterminate
# --------------------------------------------------------------------------- #
def test_unknown_tender_value_is_indeterminate():
    result = evaluate([project("9000000")], value=None)
    assert result.technical_value.passed is None


def test_unknown_closing_date_is_indeterminate():
    result = evaluate([project("9000000")], closing=None)
    assert result.technical_value.passed is None
    assert "no anchor" in result.technical_value.detail
