"""PastProject — a completed project in the company portfolio.

Used by the qualification engine (work-value evidence) and the semantic matcher
(embedded for similarity retrieval). Financials are exact decimals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PastProject:
    name: str
    client: str | None = None
    work_value: Decimal | None = None
    category: str | None = None
    location: str | None = None
    description: str | None = None
    completion_date: date | None = None
    # Vector-store bookkeeping (Phase 5).
    embedding_indexed: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def embedding_text(self) -> str:
        """Concatenated text used to compute the similarity embedding."""
        parts = [self.name, self.category, self.location, self.description]
        return " \n".join(p for p in parts if p)
