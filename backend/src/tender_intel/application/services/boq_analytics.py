"""BOQ analytics — aggregate summaries and per-category contribution.

Pure and deterministic: given the BOQ line items it computes the total value
(from known amounts only) and each category's quantity/value contribution.
"""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from tender_intel.application.dto.analytics import BOQAnalytics, BOQCategorySummary
from tender_intel.domain.entities import BOQItem
from tender_intel.domain.value_objects.unknown import is_known

_UNCATEGORISED = "Uncategorised"


def summarise(items: list[BOQItem]) -> BOQAnalytics:
    total_value = Decimal("0")
    items_with_amount = 0
    # category -> [count, quantity_sum, value_sum]
    buckets: OrderedDict[str, list[Decimal | int]] = OrderedDict()

    for item in items:
        category = item.category or _UNCATEGORISED
        bucket = buckets.setdefault(category, [0, Decimal("0"), Decimal("0")])
        bucket[0] = int(bucket[0]) + 1
        if is_known(item.quantity):
            bucket[1] = Decimal(bucket[1]) + item.quantity
        if is_known(item.amount):
            bucket[2] = Decimal(bucket[2]) + item.amount
            total_value += item.amount
            items_with_amount += 1

    categories = [
        BOQCategorySummary(
            category=name,
            item_count=int(count),
            total_quantity=Decimal(quantity),
            total_value=Decimal(value),
            value_share=(float(Decimal(value) / total_value) if total_value > 0 else 0.0),
        )
        for name, (count, quantity, value) in buckets.items()
    ]
    categories.sort(key=lambda c: c.total_value, reverse=True)

    return BOQAnalytics(
        total_items=len(items),
        items_with_amount=items_with_amount,
        total_value=total_value,
        categories=categories,
    )
