"""Completion period to exact decimal years (feature spec §1).

The point of these is that no ``float`` touches N. A float artefact here would
divide the tender value and land in a money figure a bid decision rests on.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender_intel.domain.decision.duration import parse_years


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 years", Decimal("2")),
        ("1 year", Decimal("1")),
        ("18 months", Decimal("1.5")),
        ("24 months", Decimal("2")),
        ("6 months", Decimal("0.5")),
        ("Completion period: 18 Months", Decimal("1.5")),
        ("1.5 years", Decimal("1.5")),
    ],
)
def test_exact_conversions(text, expected):
    assert parse_years(text) == expected


def test_result_is_decimal_never_float():
    value = parse_years("18 months")
    assert isinstance(value, Decimal)
    assert not isinstance(value, float)


def test_eighteen_months_is_exactly_one_and_a_half():
    # 18/12 is exact in decimal. A float round-trip would not guarantee this.
    assert parse_years("18 months") == Decimal("1.5")
    assert str(parse_years("18 months")) == "1.5"


def test_days_divide_by_the_year_constant():
    from tender_intel.domain.decision import thresholds as th

    assert parse_years("365 days") == Decimal("365") / th.DAYS_PER_YEAR
    assert parse_years("365 days") == Decimal("1")


def test_weeks_convert_through_days():
    from tender_intel.domain.decision import thresholds as th

    assert parse_years("52 weeks") == Decimal("52") * Decimal("7") / th.DAYS_PER_YEAR


@pytest.mark.parametrize("text", [None, "", "as per schedule", "12", "soon", "immediately"])
def test_unparseable_returns_none_and_never_guesses(text):
    assert parse_years(text) is None


def test_a_bare_number_is_not_assumed_to_be_months():
    # Guessing the unit is exactly what NFR-502 forbids.
    assert parse_years("12") is None


def test_negative_is_refused():
    assert parse_years("-3 months") is None
