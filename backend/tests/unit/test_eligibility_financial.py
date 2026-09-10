"""Financial criterion — min(V/N, V) against a 3-year certified average.

Feature spec §2. Marked ``regression``: these lock spec §6 thresholds and must
not be weakened without a spec change.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tender_intel.domain.decision.eligibility import (
    EligibilityEngine,
    EligibilityInput,
    TurnoverYear,
)
from tender_intel.domain.services.financial_year import FinancialYear

pytestmark = pytest.mark.regression

CRORE = Decimal("10000000")


def turnover(*amounts: str, start: int = 2022) -> list[TurnoverYear]:
    return [TurnoverYear(FinancialYear(start + i), Decimal(a)) for i, a in enumerate(amounts)]


def make(
    value: Decimal | None = CRORE,
    years: Decimal | None = Decimal("2"),
    rows: list[TurnoverYear] | None = None,
) -> EligibilityInput:
    return EligibilityInput(
        tender_value=value,
        completion_years=years,
        closing_date=date(2026, 4, 1),
        turnover_years=turnover("60000000", "60000000", "60000000") if rows is None else rows,
        matches=[],
        candidates=[],
    )


def financial(**kwargs):
    return EligibilityEngine().evaluate(make(**kwargs)).financial


# --------------------------------------------------------------------------- #
# The requirement itself
# --------------------------------------------------------------------------- #
def test_two_year_period_halves_the_requirement():
    # V = 1 Cr over 2 years -> 50 lakh.
    assert financial(value=CRORE, years=Decimal("2")).required == Decimal("5000000.00")


def test_one_year_period_requires_the_full_value():
    assert financial(value=CRORE, years=Decimal("1")).required == Decimal("10000000.00")


def test_the_cap_binds_below_one_year():
    # V/N would be 2 Cr, which exceeds V. The requirement holds at V.
    assert financial(value=CRORE, years=Decimal("0.5")).required == Decimal("10000000.00")


def test_the_cap_binds_hard_on_a_very_short_period():
    # One month: V/N is twelve times V. Still capped at V.
    result = financial(value=CRORE, years=Decimal("1") / Decimal("12"))
    assert result.required == Decimal("10000000.00")


def test_the_requirement_rounds_up_not_to_nearest():
    # 1 / 3 = 0.333... Rounding to nearest would understate the requirement.
    assert financial(value=Decimal("1"), years=Decimal("3")).required == Decimal("0.34")


def test_rounding_up_applies_to_an_exact_half():
    assert financial(value=Decimal("1"), years=Decimal("8")).required == Decimal("0.13")


# --------------------------------------------------------------------------- #
# The average
# --------------------------------------------------------------------------- #
def test_average_is_taken_over_the_recorded_years():
    result = financial(rows=turnover("1000", "2000", "3000"))
    assert result.actual == Decimal("2000.00")


def test_meets_the_requirement_exactly_passes():
    rows = turnover("5000000", "5000000", "5000000")
    result = financial(value=CRORE, years=Decimal("2"), rows=rows)
    assert result.actual == Decimal("5000000.00")
    assert result.passed is True


def test_a_shortfall_of_one_paisa_in_the_average_fails():
    # Three paisa short across the window is exactly one paisa short on average.
    rows = turnover("4999999.97", "5000000", "5000000")
    result = financial(value=CRORE, years=Decimal("2"), rows=rows)
    assert result.actual == Decimal("4999999.99")
    assert result.passed is False


def test_a_sub_paisa_shortfall_rounds_into_a_pass():
    # One paisa short across three years is a third of a paisa on average, which
    # is below the resolution the average is reported at. Recorded deliberately:
    # the average is quantised before comparison, not after.
    rows = turnover("4999999.99", "5000000", "5000000")
    result = financial(value=CRORE, years=Decimal("2"), rows=rows)
    assert result.actual == Decimal("5000000.00")
    assert result.passed is True


def test_detail_names_the_window():
    result = financial(rows=turnover("1000", "2000", "3000", start=2023))
    assert "2023-24" in result.detail
    assert "2025-26" in result.detail


# --------------------------------------------------------------------------- #
# Indeterminate — never a guess, never a partial average
# --------------------------------------------------------------------------- #
def test_unknown_tender_value_is_indeterminate():
    result = financial(value=None)
    assert result.passed is None
    assert "Tender value is UNKNOWN" in result.detail


def test_unknown_completion_period_is_indeterminate():
    result = financial(years=None)
    assert result.passed is None
    assert "Completion period is UNKNOWN" in result.detail


def test_a_non_positive_period_is_indeterminate_not_a_division_error():
    assert financial(years=Decimal("0")).passed is None


@pytest.mark.parametrize("count", [0, 1, 2])
def test_fewer_than_three_recorded_years_is_indeterminate(count):
    rows = turnover(*["1000"] * count)
    result = financial(rows=rows)
    assert result.passed is None
    assert "of the 3 completed financial years" in result.detail


def test_three_recorded_years_is_enough():
    assert financial(rows=turnover("1000", "1000", "1000")).passed is not None


def test_required_and_actual_are_decimal_never_float():
    result = financial()
    assert isinstance(result.required, Decimal)
    assert isinstance(result.actual, Decimal)
