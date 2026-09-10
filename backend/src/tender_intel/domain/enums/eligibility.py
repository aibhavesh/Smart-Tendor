"""Eligibility screening enums (feature spec §1, §3, §4).

``EligibilityStatus`` carries three values, not two. ``INDETERMINATE`` is
deliberately *not* grouped under ``ELIGIBLE``: it routes to REVIEW through §13.3
rule 1b so that a tender the screen could not decide reaches a person rather than
being reported as passing. Grouping it under ``NOT_ELIGIBLE`` instead would make an
under-populated turnover table return NO_BID for every tender.
"""

from __future__ import annotations

from enum import StrEnum


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    INDETERMINATE = "INDETERMINATE"


class MatchMethod(StrEnum):
    """Which cascade stage produced a work-type match. First hit wins."""

    EXACT = "EXACT"
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"


class MatchGrade(StrEnum):
    """Band a match score falls into.

    ``REVIEW`` is a pass that carries doubt: the work type joins the candidate
    pool, but the screen reports INDETERMINATE rather than ELIGIBLE.
    """

    MATCHED = "MATCHED"
    REVIEW = "REVIEW"
    NO_MATCH = "NO_MATCH"


#: Which of the three nested similar-work rules a technical pass satisfied.
#: Nested by construction — a project clearing 60% also clears 40% and 30% — so
#: the first satisfied rule is recorded and the others are never counted.
class SimilarWorkRule(StrEnum):
    ONE_AT_60 = "1x60"
    TWO_AT_40 = "2x40"
    THREE_AT_30 = "3x30"
