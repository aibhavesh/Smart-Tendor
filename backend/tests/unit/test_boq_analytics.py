"""Phase 4 BOQ analytics tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from tender_intel.application.services.boq_analytics import summarise
from tender_intel.domain.entities import BOQItem
from tender_intel.domain.value_objects.unknown import UNKNOWN

TENDER = uuid4()


def _item(category, amount, quantity=UNKNOWN):
    return BOQItem(
        tender_id=TENDER,
        description="x",
        category=category,
        amount=amount,
        quantity=quantity,
    )


def test_per_category_value_and_share():
    analytics = summarise(
        [
            _item("Civil", Decimal("100")),
            _item("Civil", Decimal("50")),
            _item("Electrical", Decimal("50")),
            _item(None, UNKNOWN, quantity=Decimal("10")),
        ]
    )
    assert analytics.total_items == 4
    assert analytics.items_with_amount == 3
    assert analytics.total_value == Decimal("200")

    # Sorted by value descending.
    civil, electrical, uncategorised = analytics.categories
    assert civil.category == "Civil"
    assert civil.total_value == Decimal("150")
    assert civil.value_share == 0.75
    assert electrical.value_share == 0.25
    assert uncategorised.category == "Uncategorised"
    assert uncategorised.total_quantity == Decimal("10")
    assert uncategorised.value_share == 0.0


def test_empty_boq():
    analytics = summarise([])
    assert analytics.total_items == 0
    assert analytics.total_value == Decimal("0")
    assert analytics.categories == []
