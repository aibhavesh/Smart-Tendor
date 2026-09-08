"""Whether a recorded verdict has been superseded by a later correction.

Recommendations on this platform are **not** stored — every read recomputes
them from live metadata — so a recommendation can never be stale. What *can*
go stale is a recorded human verdict: a manager approves a bid, someone later
corrects the tender value it was judged on, and the decision on file now rests
on evidence that has changed.

This is a warning, not a correction. Nothing is recomputed, invalidated or
hidden; the flag exists so a superseded decision is never presented as current.
"""

from __future__ import annotations

from datetime import datetime


def verdict_is_stale(
    last_verdict_at: datetime | None, metadata_updated_at: datetime | None
) -> bool:
    """True when metadata was corrected after the most recent verdict.

    Compared **strictly**, so an equal pair of timestamps reads as current.
    That matters in two places: PostgreSQL's ``now()`` is transaction-start
    time while ``TenderReview.created_at`` is Python wall-clock, and SQLite's
    ``CURRENT_TIMESTAMP`` is only second-granular. A verdict that applies
    corrections on its way through must never flag itself, and strict
    comparison plus the write order (corrections first, record second)
    guarantees it cannot.
    """
    if last_verdict_at is None or metadata_updated_at is None:
        return False
    return metadata_updated_at > last_verdict_at
