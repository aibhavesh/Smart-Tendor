"""Human-review record kinds and verdicts (Phase 8).

A review record is one of two things, and the difference is recorded
explicitly rather than inferred from whether a verdict happens to be present:

* ``CORRECTION`` — someone fixed an extracted field. No decision was made and
  the tender does not move.
* ``VERDICT`` — a manager decided. This is the bid decision.

Keeping ``kind`` explicit means review history and audit diffs never have to
guess what a row meant, and a correction can never be read as a decision.
"""

from __future__ import annotations

from enum import StrEnum


class ReviewKind(StrEnum):
    CORRECTION = "CORRECTION"
    VERDICT = "VERDICT"


class ReviewVerdict(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
