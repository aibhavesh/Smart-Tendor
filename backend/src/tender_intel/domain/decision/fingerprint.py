"""Input fingerprint for a stored eligibility result (feature spec §7).

Staleness is derived, never stored. A screen records the fingerprint of what it
read; a later reader recomputes it and compares. A mismatch means the inputs have
moved and the stored verdict no longer describes them.

This mirrors how verdict staleness already works in
``domain/services/staleness.py``: nothing is recomputed, invalidated or hidden,
and no flag has to be flipped by whoever changed the data. The portfolio counter
is what makes that free — every mutation to a project, work type, alias or tag
bumps it, so a new mutation path invalidates without knowing this module exists.

Serialisation is canonical and ordered so the same inputs always hash the same
way: an UNKNOWN is a literal sentinel rather than an empty string, decimals go in
as their exact string form, and the turnover years are sorted by label.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

_UNKNOWN = "UNKNOWN"
_SEPARATOR = "\x1f"  # unit separator: cannot occur in any serialised field


def _decimal(value: Decimal | None) -> str:
    return _UNKNOWN if value is None else str(value)


def _date(value: date | None) -> str:
    return _UNKNOWN if value is None else value.isoformat()


def compute_fingerprint(
    *,
    tender_value: Decimal | None,
    completion_years: Decimal | None,
    closing_date: date | None,
    turnover_years: list[tuple[str, Decimal]],
    portfolio_counter: int,
) -> str:
    """Return the SHA-256 hex digest of this evaluation's inputs."""
    parts = [
        f"v={_decimal(tender_value)}",
        f"n={_decimal(completion_years)}",
        f"closing={_date(closing_date)}",
        "turnover=" + ",".join(f"{label}:{amount}" for label, amount in sorted(turnover_years)),
        f"portfolio={portfolio_counter}",
    ]
    return hashlib.sha256(_SEPARATOR.join(parts).encode("utf-8")).hexdigest()


def is_stale(stored: str | None, current: str) -> bool:
    """True when a stored result no longer describes the current inputs.

    A result with no recorded fingerprint reads as stale: it predates this
    mechanism, so nothing vouches for it.
    """
    return stored != current
