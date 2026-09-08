"""Tender lifecycle status and the allowed transitions.

Data flow (Implementation Plan §6): nothing analyses before PARSED, no
recommendation before the engines. The lifecycle encodes that ordering:

    REGISTERED -> DOWNLOADED -> PARSED -> ANALYZED -> REVIEWED

Any state may be ARCHIVED. A REVIEWED tender may return to ANALYZED to support
re-analysis after a correction. Terminal: ARCHIVED.
"""

from __future__ import annotations

from enum import StrEnum


class TenderStatus(StrEnum):
    REGISTERED = "REGISTERED"
    DOWNLOADED = "DOWNLOADED"
    PARSED = "PARSED"
    ANALYZED = "ANALYZED"
    REVIEWED = "REVIEWED"
    ARCHIVED = "ARCHIVED"

    def can_transition_to(self, target: TenderStatus) -> bool:
        return target in _TRANSITIONS[self]


_TRANSITIONS: dict[TenderStatus, frozenset[TenderStatus]] = {
    TenderStatus.REGISTERED: frozenset({TenderStatus.DOWNLOADED, TenderStatus.ARCHIVED}),
    TenderStatus.DOWNLOADED: frozenset({TenderStatus.PARSED, TenderStatus.ARCHIVED}),
    TenderStatus.PARSED: frozenset({TenderStatus.ANALYZED, TenderStatus.ARCHIVED}),
    TenderStatus.ANALYZED: frozenset(
        {TenderStatus.REVIEWED, TenderStatus.PARSED, TenderStatus.ARCHIVED}
    ),
    TenderStatus.REVIEWED: frozenset({TenderStatus.ANALYZED, TenderStatus.ARCHIVED}),
    TenderStatus.ARCHIVED: frozenset(),
}
