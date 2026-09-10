"""TenderReview — a correction or a verdict, with before/after snapshots (Phase 8).

One record type, discriminated by :class:`ReviewKind`. A correction carries no
verdict and moves nothing; a verdict is the bid decision. Both capture the
before/after pair, because a verdict may correct fields on its way through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from tender_intel.domain.enums.review import ReviewKind, ReviewVerdict
from tender_intel.domain.exceptions import DomainValidationError


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class TenderReview:
    tender_id: UUID
    reviewer_id: UUID
    kind: ReviewKind
    verdict: ReviewVerdict | None = None
    comments: str | None = None
    # Snapshots of the reviewed values before and after any correction.
    before_snapshot: dict[str, Any] = field(default_factory=dict)
    after_snapshot: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        # ``kind`` is authoritative and stored; this only stops the two fields
        # from contradicting each other.
        if self.kind is ReviewKind.VERDICT and self.verdict is None:
            raise DomainValidationError("a VERDICT record must carry a verdict")
        if self.kind is ReviewKind.CORRECTION and self.verdict is not None:
            raise DomainValidationError("a CORRECTION record must not carry a verdict")

    @property
    def is_verdict(self) -> bool:
        return self.kind is ReviewKind.VERDICT
