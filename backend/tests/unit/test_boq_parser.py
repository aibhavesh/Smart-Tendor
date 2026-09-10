"""Phase 4 BOQ table-parsing tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from tender_intel.domain.value_objects.unknown import is_known
from tender_intel.infrastructure.extraction.boq_parser import parse_boq_tables

TENDER = uuid4()

TABLE = [
    ["S.No", "Description", "Unit", "Quantity", "Rate", "Amount"],
    ["1", "Earthwork excavation", "Cum", "120.5", "85", "10242.50"],
    ["2", "PCC 1:4:8", "Cum", "50", "", ""],  # rate/amount blank -> UNKNOWN
    ["", "Total", "", "", "", "10242.50"],  # total row -> skipped
]


def test_parses_rows_with_unknown_for_blank_numeric():
    items = parse_boq_tables([TABLE], TENDER)
    assert len(items) == 2

    first = items[0]
    assert first.description == "Earthwork excavation"
    assert first.unit == "Cum"
    assert first.quantity == Decimal("120.5")
    assert first.unit_rate == Decimal("85")
    assert first.amount == Decimal("10242.50")
    assert first.confidence == 0.8  # all three numerics parsed

    second = items[1]
    assert second.quantity == Decimal("50")
    assert not is_known(second.unit_rate)
    assert not is_known(second.amount)
    assert second.confidence == 0.6  # only quantity parsed


def test_table_without_recognisable_header_is_ignored():
    junk = [["foo", "bar"], ["1", "2"]]
    assert parse_boq_tables([junk], TENDER) == []


def test_category_column_is_captured():
    table = [
        ["Description", "Category", "Amount"],
        ["Cable laying", "Electrical", "5000"],
    ]
    items = parse_boq_tables([table], TENDER)
    assert items[0].category == "Electrical"
