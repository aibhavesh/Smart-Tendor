"""Indian financial-year arithmetic (feature spec §2)."""

from __future__ import annotations

from datetime import date

import pytest

from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.domain.services.financial_year import (
    FinancialYear,
    completed_years_before,
    fy_containing,
    latest_completed,
    parse_label,
)


def test_label_format():
    assert FinancialYear(2025).label == "2025-26"
    assert FinancialYear(1999).label == "1999-00"
    assert FinancialYear(2009).label == "2009-10"


def test_year_boundaries():
    year = FinancialYear(2025)
    assert year.start_date == date(2025, 4, 1)
    assert year.end_date == date(2026, 3, 31)


@pytest.mark.parametrize(
    ("day", "expected_start"),
    [
        (date(2025, 4, 1), 2025),  # first day of the year
        (date(2025, 12, 31), 2025),
        (date(2026, 3, 31), 2025),  # last day of the year
        (date(2026, 4, 1), 2026),  # first day of the next
        (date(2026, 1, 1), 2025),  # January falls in the year that opened last April
    ],
)
def test_fy_containing(day, expected_start):
    assert fy_containing(day).start_year == expected_start


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        # A year is completed only when its 31 March close is STRICTLY before the
        # anchor, so on the closing day itself it is still running.
        (date(2026, 3, 31), "2024-25"),
        (date(2026, 4, 1), "2025-26"),
        (date(2026, 6, 15), "2025-26"),
    ],
)
def test_latest_completed_is_strict(anchor, expected):
    assert latest_completed(anchor).label == expected


def test_completed_window_is_oldest_first():
    window = completed_years_before(date(2026, 4, 1), 3)
    assert [y.label for y in window] == ["2023-24", "2024-25", "2025-26"]


def test_seven_year_window_spans_seven_years():
    window = completed_years_before(date(2026, 4, 1), 7)
    assert len(window) == 7
    assert window[0].label == "2019-20"
    assert window[-1].label == "2025-26"


def test_window_anchors_shift_by_one_across_31_march():
    before = completed_years_before(date(2026, 3, 31), 3)
    after = completed_years_before(date(2026, 4, 1), 3)
    assert before[-1].label == "2024-25"
    assert after[-1].label == "2025-26"


def test_completed_years_rejects_a_zero_count():
    with pytest.raises(DomainValidationError):
        completed_years_before(date(2026, 4, 1), 0)


def test_parse_label_roundtrips():
    assert parse_label("2025-26") == FinancialYear(2025)
    assert parse_label("  2025-26 ") == FinancialYear(2025)


@pytest.mark.parametrize("bad", ["2025", "2025-2026", "25-26", "2025/26", "", "2025-27"])
def test_parse_label_rejects_malformed(bad):
    # 2025-27 names no financial year and is refused rather than coerced.
    with pytest.raises(DomainValidationError):
        parse_label(bad)


def test_contains():
    year = FinancialYear(2025)
    assert year.contains(date(2025, 4, 1))
    assert year.contains(date(2026, 3, 31))
    assert not year.contains(date(2026, 4, 1))
