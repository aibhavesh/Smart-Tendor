"""Phase 3 Excel bulk-import parsing tests."""

from __future__ import annotations

import io

from openpyxl import Workbook

from tender_intel.infrastructure.excel import parse_rows


def _workbook(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_parse_maps_headers_and_skips_blank_rows():
    content = _workbook(
        [
            ["Tender Number", "Title", "Estimated Value"],
            ["T-1", "Road work", 1000000],
            [None, None, None],  # blank -> skipped
            ["T-2", "Bridge", 5000000],
        ]
    )
    rows = list(parse_rows(content))
    assert [n for n, _ in rows] == [2, 4]  # row numbers, blank skipped
    # Headings normalise onto the canonical field names bulk_import reads.
    assert rows[0][1]["tender_number"] == "T-1"
    assert rows[0][1]["estimated_value"] == 1000000


def test_parse_empty_workbook():
    assert list(parse_rows(_workbook([]))) == []


def test_parse_header_only():
    assert list(parse_rows(_workbook([["tender_number", "title"]]))) == []


def test_canonical_headers_still_resolve():
    """The documented header spelling keeps working alongside the aliases."""
    content = _workbook(
        [
            ["tender_number", "title", "source_url"],
            ["T-9", "Culvert", "https://example.test/a.pdf"],
        ]
    )
    _, record = next(iter(parse_rows(content)))
    assert record["tender_number"] == "T-9"
    assert record["title"] == "Culvert"
    assert record["source_url"] == "https://example.test/a.pdf"


def test_real_world_headings_are_aliased():
    """The shape the railway tender sheet is actually kept in."""
    content = _workbook(
        [
            ["TENDER NO.", "WORK", "VALUE", "DIVISION", "TENDER LINK", "Date"],
            [
                "SG-DSE-OT-05-26",
                "Provision of Railnet connectivity",
                19635253.31,
                "EAST CENTRAL RLY",
                "https://example.test/nit.pdf",
                "2026-06-05",
            ],
        ]
    )
    _, record = next(iter(parse_rows(content)))
    assert record["tender_number"] == "SG-DSE-OT-05-26"
    assert record["title"] == "Provision of Railnet connectivity"
    assert record["estimated_value"] == 19635253.31
    assert record["department"] == "EAST CENTRAL RLY"
    assert record["source_url"] == "https://example.test/nit.pdf"
    assert record["closing_date"] == "2026-06-05"


def test_extra_columns_fold_into_description():
    """Columns with no field of their own survive as a labelled description."""
    content = _workbook(
        [
            ["TENDER NO.", "WORK", "LOCATION", "EMD", "SIMILAR WORK"],
            ["T-3", "Signalling", "BIKANER", 369200, "Any telecom work."],
        ]
    )
    _, record = next(iter(parse_rows(content)))
    description = record["description"]
    assert "LOCATION: BIKANER" in description
    assert "EMD: 369200" in description
    assert "SIMILAR WORK: Any telecom work." in description


def test_description_column_is_preserved_ahead_of_folded_extras():
    content = _workbook(
        [
            ["tender_number", "title", "description", "LOCATION"],
            ["T-4", "Bridge", "Original text.", "MUMBAI"],
        ]
    )
    _, record = next(iter(parse_rows(content)))
    assert record["description"].startswith("Original text.")
    assert "LOCATION: MUMBAI" in record["description"]
