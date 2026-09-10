"""Indian financial years (feature spec §2).

A financial year runs 1 April to 31 March and is labelled by the calendar year it
opens in: the year opening 1 April 2025 and closing 31 March 2026 is ``2025-26``.

A year is *completed* relative to an anchor when its 31 March close falls
**strictly** before that anchor. A tender closing on 31 March 2026 therefore sees
2024-25 as its most recent completed year, and one closing a day later sees
2025-26. The strictness matters: on the closing day itself the year is still
running, and averaging turnover over a year that has not finished would report a
figure no certificate can support.

Both windows in the eligibility screen anchor to the **tender closing date**,
never to the current date, so re-evaluating a tender months later reproduces the
same result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from tender_intel.domain.exceptions import DomainValidationError

_FY_START_MONTH = 4
_FY_LABEL = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True, slots=True, order=True)
class FinancialYear:
    """The year opening 1 April of ``start_year``."""

    start_year: int

    @property
    def label(self) -> str:
        return f"{self.start_year}-{(self.start_year + 1) % 100:02d}"

    @property
    def start_date(self) -> date:
        return date(self.start_year, _FY_START_MONTH, 1)

    @property
    def end_date(self) -> date:
        return date(self.start_year + 1, _FY_START_MONTH - 1, 31)

    def previous(self) -> FinancialYear:
        return FinancialYear(self.start_year - 1)

    def is_completed_by(self, anchor: date) -> bool:
        return self.end_date < anchor

    def contains(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.label


def fy_containing(day: date) -> FinancialYear:
    """The financial year ``day`` falls inside."""
    start = day.year if day.month >= _FY_START_MONTH else day.year - 1
    return FinancialYear(start)


def latest_completed(anchor: date) -> FinancialYear:
    """The most recent financial year fully elapsed before ``anchor``.

    The year containing the anchor is by definition still running, so this is
    always the one before it. That holds on every day of the year, including
    31 March, because the previous year closed on 31 March of the anchor year's
    opening calendar year.
    """
    return fy_containing(anchor).previous()


def completed_years_before(anchor: date, count: int) -> list[FinancialYear]:
    """The ``count`` most recent completed years, oldest first.

    Ordered oldest first so a rendered list reads chronologically and the
    fingerprint's serialisation is stable.
    """
    if count < 1:
        raise DomainValidationError("count must be at least 1")
    newest = latest_completed(anchor)
    years = [FinancialYear(newest.start_year - offset) for offset in range(count)]
    return sorted(years)


def parse_label(label: str) -> FinancialYear:
    """Parse a ``2025-26`` label, rejecting anything that is not one.

    The two-digit tail must be the opening year's successor. ``2025-27`` names no
    financial year and is refused rather than coerced to the nearest one.
    """
    match = _FY_LABEL.match(label.strip())
    if match is None:
        raise DomainValidationError(f"{label!r} is not a financial-year label (expected 'YYYY-YY')")
    start_year = int(match.group(1))
    if (start_year + 1) % 100 != int(match.group(2)):
        raise DomainValidationError(f"{label!r} does not name a consecutive financial year")
    return FinancialYear(start_year)
