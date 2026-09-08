"""The bid recommendation verdict (PRD Section 13.3)."""

from __future__ import annotations

from enum import StrEnum


class RecommendationVerdict(StrEnum):
    GO = "GO"
    REVIEW = "REVIEW"
    NO_BID = "NO_BID"
