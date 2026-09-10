"""BOQItem — a single Bill-of-Quantities line item.

Quantities, rates and amounts are exact :class:`~decimal.Decimal`. Absent
values are :data:`UNKNOWN`; ``confidence`` reflects extraction trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

from tender_intel.domain.value_objects.unknown import UNKNOWN, Maybe


@dataclass(slots=True)
class BOQItem:
    tender_id: UUID
    item_number: str | None = None
    description: str = ""
    unit: str | None = None
    quantity: Maybe[Decimal] = UNKNOWN
    unit_rate: Maybe[Decimal] = UNKNOWN
    amount: Maybe[Decimal] = UNKNOWN
    category: str | None = None
    page_number: int | None = None
    confidence: float = 0.0
    id: UUID = field(default_factory=uuid4)
