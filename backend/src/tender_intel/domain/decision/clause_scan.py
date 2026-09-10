"""Pure clause-detection helpers for the risk engine (stdlib only).

Detects a category's keyword vocabulary in tender text and, where relevant,
parses the percentage magnitude associated with it. Kept in the domain because
it is decision logic (the per-category vocabularies live in ``thresholds``), not
generic extraction.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# A percentage written as "10%", "10 %", "10 percent" or "10 per cent".
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)", re.IGNORECASE)
_WINDOW = 120  # chars after a keyword to search for its percentage


@dataclass(frozen=True, slots=True)
class ClauseHit:
    present: bool
    percent: Decimal | None


def contains_any(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def scan_percent_clause(text: str, keywords: Sequence[str]) -> ClauseHit:
    """Whether any keyword is present and, if so, the nearest following percent."""
    lowered = text.lower()
    present = False
    for kw in keywords:
        index = lowered.find(kw)
        if index == -1:
            continue
        present = True
        window = lowered[index : index + len(kw) + _WINDOW]
        match = _PERCENT_RE.search(window)
        if match:
            try:
                return ClauseHit(present=True, percent=Decimal(match.group(1)))
            except InvalidOperation:  # pragma: no cover - defensive
                return ClauseHit(present=True, percent=None)
    return ClauseHit(present=present, percent=None)
