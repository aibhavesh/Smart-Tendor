"""Completion period to exact decimal years (feature spec §1).

The existing ``parse_days`` and ``parse_months`` in the extraction layer both
route through ``float()``. Neither can be reused here: N divides the tender value
in ``min(V / N, V)``, so a float artefact would land directly in a money figure a
bid decision rests on.

Nothing is guessed. A period with no recognisable unit returns ``None`` and the
screen reports the tender indeterminate rather than assuming months.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from tender_intel.domain.decision import thresholds as th

# The sign is captured so a negative duration is refused rather than silently
# read as its absolute value.
_DURATION = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(day|week|month|year)s?\b", re.IGNORECASE)
_MONTHS_PER_YEAR = Decimal("12")
_DAYS_PER_WEEK = Decimal("7")


def parse_years(text: str | None) -> Decimal | None:
    """Parse a completion period into exact decimal years.

    Eighteen months is exactly ``1.5``. A day-denominated period divides by
    ``DAYS_PER_YEAR``, which is the one place that conversion rate is applied.
    """
    if not text:
        return None
    match = _DURATION.search(text)
    if match is None:
        return None
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation:  # pragma: no cover - defensive
        return None
    if amount < 0:
        return None

    unit = match.group(2).lower()
    if unit == "year":
        return amount
    if unit == "month":
        return amount / _MONTHS_PER_YEAR
    if unit == "week":
        return amount * _DAYS_PER_WEEK / th.DAYS_PER_YEAR
    return amount / th.DAYS_PER_YEAR
