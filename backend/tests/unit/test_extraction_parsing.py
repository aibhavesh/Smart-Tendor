"""Phase 4 value-parsing tests (amounts, quantities, dates)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tender_intel.infrastructure.extraction.parsing import (
    parse_amount,
    parse_date,
    parse_months,
    parse_quantity,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("₹ 1,50,00,000", Decimal("15000000")),
        ("Rs. 1.5 Crore", Decimal("15000000")),
        ("15 Lakh", Decimal("1500000")),
        ("Rs 5000", Decimal("5000")),
        ("INR 2,50,000", Decimal("250000")),
        ("1.25 cr", Decimal("12500000")),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["", "not a number", "-500"])
def test_parse_amount_rejects(text):
    assert parse_amount(text) is None


def test_parse_quantity():
    assert parse_quantity("120.50 Cum") == Decimal("120.50")
    assert parse_quantity("1,000 nos") == Decimal("1000")
    assert parse_quantity("abc") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01/09/2026", date(2026, 9, 1)),
        ("15-08-2026", date(2026, 8, 15)),
        ("2026-09-01", date(2026, 9, 1)),
        ("1 September 2026", date(2026, 9, 1)),
        ("Last date: 15/09/2026", date(2026, 9, 15)),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_parse_date_rejects_garbage():
    assert parse_date("sometime next year") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("12 months", 12), ("18 Months", 18), ("2 years", 24), ("1.5 years", 18), ("soon", None)],
)
def test_parse_months(text, expected):
    assert parse_months(text) == expected
