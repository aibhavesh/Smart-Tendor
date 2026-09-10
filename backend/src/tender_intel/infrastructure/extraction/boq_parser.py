"""Pure mapping of extracted tables to BOQ line items.

Header-aware: locates the column header row by keyword, maps columns, then
converts each data row to a :class:`BOQItem`. Unparseable numeric cells become
:data:`UNKNOWN` (never guessed); total/subtotal rows are skipped.
"""

from __future__ import annotations

from uuid import UUID

from tender_intel.domain.entities import BOQItem
from tender_intel.domain.interfaces.providers import Table
from tender_intel.domain.value_objects.unknown import UNKNOWN, Maybe
from tender_intel.infrastructure.extraction.parsing import parse_amount, parse_quantity

# Column role -> keywords that identify its header cell.
_COLUMN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "item_number": ("s.no", "s no", "sl.no", "sl no", "sr.no", "item no", "sno", "srno"),
    "description": ("description", "particular", "item of work", "nature of work"),
    "unit": ("unit", "uom"),
    "quantity": ("qty", "quantity", "nos"),
    "unit_rate": ("rate", "unit rate"),
    "amount": ("amount", "value", "total"),
    "category": ("category", "group", "head", "section"),
}
_TOTAL_MARKERS = ("total", "grand total", "sub total", "sub-total", "g.total")


def _norm(cell: str | None) -> str:
    return (cell or "").strip().lower()


def _detect_columns(row: list[str | None]) -> dict[str, int] | None:
    mapping: dict[str, int] = {}
    for index, cell in enumerate(row):
        text = _norm(cell)
        if not text:
            continue
        for role, keywords in _COLUMN_KEYWORDS.items():
            if role in mapping:
                continue
            if any(kw in text for kw in keywords):
                mapping[role] = index
                break
    # A row is a header only if it names a description and at least one numeric col.
    if "description" in mapping and ({"quantity", "unit_rate", "amount"} & mapping.keys()):
        return mapping
    return None


def _cell(row: list[str | None], columns: dict[str, int], role: str) -> str | None:
    idx = columns.get(role)
    if idx is None or idx >= len(row):
        return None
    value = row[idx]
    return value.strip() if isinstance(value, str) else value


def _maybe_amount(text: str | None) -> Maybe[object]:
    if not text:
        return UNKNOWN
    parsed = parse_amount(text)
    return UNKNOWN if parsed is None else parsed


def _maybe_quantity(text: str | None) -> Maybe[object]:
    if not text:
        return UNKNOWN
    parsed = parse_quantity(text)
    return UNKNOWN if parsed is None else parsed


def parse_boq_tables(tables: list[Table], tender_id: UUID) -> list[BOQItem]:
    items: list[BOQItem] = []
    for table in tables:
        columns: dict[str, int] | None = None
        for row in table:
            if columns is None:
                columns = _detect_columns(row)
                continue
            description = _cell(row, columns, "description")
            if not description or not str(description).strip():
                continue
            if _norm(str(description)).startswith(_TOTAL_MARKERS):
                continue

            quantity = _maybe_quantity(_str(_cell(row, columns, "quantity")))
            unit_rate = _maybe_amount(_str(_cell(row, columns, "unit_rate")))
            amount = _maybe_amount(_str(_cell(row, columns, "amount")))
            parsed_count = sum(v is not UNKNOWN for v in (quantity, unit_rate, amount))

            items.append(
                BOQItem(
                    tender_id=tender_id,
                    item_number=_str(_cell(row, columns, "item_number")),
                    description=str(description).strip(),
                    unit=_str(_cell(row, columns, "unit")),
                    quantity=quantity,  # type: ignore[arg-type]
                    unit_rate=unit_rate,  # type: ignore[arg-type]
                    amount=amount,  # type: ignore[arg-type]
                    category=_str(_cell(row, columns, "category")),
                    confidence=min(0.5 + 0.1 * parsed_count, 0.8),
                )
            )
    return items


def _str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
