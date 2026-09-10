"""Tender aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import InvalidStatusTransitionError


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Tender:
    tender_number: str
    title: str
    status: TenderStatus = TenderStatus.REGISTERED
    description: str | None = None
    estimated_value: Decimal | None = None  # optional per PRD
    closing_date: date | None = None  # optional per PRD
    source_url: str | None = None
    department: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def transition_to(self, target: TenderStatus) -> None:
        """Advance the lifecycle, enforcing the transition rules."""
        if not self.status.can_transition_to(target):
            raise InvalidStatusTransitionError("Tender", self.status, target)
        self.status = target
        self.updated_at = _now()
