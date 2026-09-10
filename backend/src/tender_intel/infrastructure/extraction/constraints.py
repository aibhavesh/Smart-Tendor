"""Parse numeric eligibility constraints from tender text (crore/lakh aware)."""

from __future__ import annotations

import re
from decimal import Decimal

from tender_intel.infrastructure.extraction.parsing import parse_amount

# Captures the amount phrase following a minimum-value cue.
_MIN_VALUE_RE = re.compile(
    r"(?:not less than|at\s?least|minimum(?:\s+value)?|min\.?|value\s+of(?:\s+not\s+less\s+than)?)"
    r"\s*(?:rs\.?|₹|inr)?\s*"
    r"([\d][\d,]*\.?\d*\s*(?:crore|cr|lakh|lac|lacs)?)",
    re.IGNORECASE,
)


def parse_min_value(text: str | None) -> Decimal | None:
    """Extract a minimum required value (e.g. 'not less than Rs. 1 crore')."""
    if not text:
        return None
    match = _MIN_VALUE_RE.search(text)
    if not match:
        return None
    return parse_amount(match.group(1))
