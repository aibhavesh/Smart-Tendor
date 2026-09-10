"""BOQ analytics DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BOQCategorySummary:
    category: str
    item_count: int
    total_quantity: Decimal
    total_value: Decimal
    value_share: float  # fraction of the overall BOQ value (0..1)


@dataclass(slots=True)
class BOQAnalytics:
    total_items: int = 0
    items_with_amount: int = 0
    total_value: Decimal = Decimal("0")
    categories: list[BOQCategorySummary] = field(default_factory=list)
