"""Past-project application DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PastProjectCreate:
    name: str
    client: str | None = None
    work_value: Decimal | None = None
    category: str | None = None
    location: str | None = None
    description: str | None = None
    completion_date: date | None = None


@dataclass(frozen=True, slots=True)
class PastProjectPatch:
    name: str | None = None
    client: str | None = None
    work_value: Decimal | None = None
    category: str | None = None
    location: str | None = None
    description: str | None = None
    completion_date: date | None = None
