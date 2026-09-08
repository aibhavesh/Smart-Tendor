"""Semantic-matching DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    project_id: UUID
    name: str
    similarity: float
    eligible: bool
    work_value: Decimal | None
    category: str | None
    location: str | None
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MatchResult:
    query: str
    min_required_value: Decimal | None
    candidates: list[MatchCandidate]
