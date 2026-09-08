"""Phase 5 numeric eligibility-constraint parsing tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender_intel.infrastructure.extraction.constraints import parse_min_value


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("similar work of value not less than Rs. 1 crore", Decimal("10000000")),
        ("minimum value of Rs. 50 lakh", Decimal("5000000")),
        ("at least 2 Crore", Decimal("20000000")),
        ("completed works of value of not less than ₹ 75,00,000", Decimal("7500000")),
    ],
)
def test_parse_min_value(text, expected):
    assert parse_min_value(text) == expected


@pytest.mark.parametrize("text", [None, "", "no numeric criterion stated here"])
def test_parse_min_value_none(text):
    assert parse_min_value(text) is None
