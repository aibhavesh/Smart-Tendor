"""Portfolio workbook (.xlsx) parsing for bulk past-project import.

Reuses :func:`tender_intel.infrastructure.excel.parse_rows` — the reader written
for the tender workbook — with a past-project heading map. Only the vocabulary
differs; the row iteration, heading normalisation and blank-row skipping are the
same code.

The portfolio workbook is dirty in known, specific ways, and each is handled by
a parser that already exists rather than a second one written here:

* LOA names carry embedded newlines and trailing whitespace. The matching key is
  :func:`normalise_alias`, the same pinned normaliser the work-type seed loader
  reconciles LOA references with, so a reference imported here and a reference
  named in ``work_types_seed.json`` collapse to the same key. Storage keeps the
  original casing with only whitespace runs collapsed, because the reference is
  shown to people.
* Amounts arrive comma-grouped, prefixed with a currency symbol, suffixed with
  ``Cr``/``Lakh``, and sometimes with junk after a newline. :func:`parse_amount`
  already handles all four and returns an exact ``Decimal``.
* Dates arrive as real datetimes from openpyxl, or as text in several formats.
  :func:`parse_date` already tries the formats in turn.
* The completion-certificate column sometimes reads ``Running`` rather than a
  date. That is not a parse failure and must not be discarded: it means the work
  is ongoing. It is recorded verbatim in ``completion_certificate_note`` with the
  date left ``None`` — which is exactly what the eligibility engine's stage B
  reads as "not yet evidence".
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from tender_intel.domain.decision.normalise import normalise_alias
from tender_intel.infrastructure.excel import parse_rows
from tender_intel.infrastructure.extraction.parsing import parse_amount, parse_date

_WHITESPACE = re.compile(r"\s+")

#: Heading text (normalised) -> canonical PastProject field.
PROJECT_HEADER_ALIASES: dict[str, str] = {
    # --- name ---
    "work": "name",
    "name of work": "name",
    "work description": "name",
    "description of work": "name",
    "project": "name",
    "project name": "name",
    "work name": "name",
    # --- client ---
    "client": "client",
    "customer": "client",
    "employer": "client",
    "railway": "client",
    "zone": "client",
    "division": "client",
    "department": "client",
    "organisation": "client",
    "organization": "client",
    # --- work_value ---
    "value": "work_value",
    "work value": "work_value",
    "order value": "work_value",
    "contract value": "work_value",
    "amount": "work_value",
    "po value": "work_value",
    "loa value": "work_value",
    "project value": "work_value",
    # --- loa_reference ---
    "loa": "loa_reference",
    "loa no": "loa_reference",
    "loa ref": "loa_reference",
    "loa reference": "loa_reference",
    "loa name": "loa_reference",
    "work order no": "loa_reference",
    "po no": "loa_reference",
    "reference": "loa_reference",
    # --- completion_date ---
    "completion date": "completion_date",
    "date of completion": "completion_date",
    "completed on": "completion_date",
    # --- completion_certificate_date ---
    "completion certificate": "completion_certificate_date",
    "completion certificate date": "completion_certificate_date",
    "cc date": "completion_certificate_date",
    "certificate date": "completion_certificate_date",
    "pcc": "completion_certificate_date",
    # --- location ---
    "location": "location",
    "site": "location",
    "work area": "location",
    "place": "location",
    # --- category ---
    "category": "category",
    "type": "category",
    "work type": "category",
    "nature of work": "category",
}

#: Columns worth keeping but with no field of their own, folded into the
#: description so detail survives instead of being dropped.
DESCRIPTION_COLUMNS: tuple[str, ...] = ("scope", "remarks", "status", "quantity", "duration")


def collapse_whitespace(text: str) -> str:
    """Collapse whitespace runs and strip, preserving case.

    The display form of an LOA reference. :func:`normalise_alias` is the *matching*
    form; it casefolds, which would misrepresent a reference shown to a reviewer.
    """
    return _WHITESPACE.sub(" ", text).strip()


def reference_key(text: str) -> str:
    """The reconciliation key for an LOA reference."""
    return normalise_alias(text)


def build_description(record: dict[str, Any]) -> str | None:
    """Fold the extra columns into one labelled block."""
    parts: list[str] = []
    existing = record.get("description")
    if existing is not None and str(existing).strip():
        parts.append(collapse_whitespace(str(existing)))
    for column in DESCRIPTION_COLUMNS:
        value = record.get(column.replace(" ", "_"))
        if value is None or not str(value).strip():
            continue
        parts.append(f"{column.upper()}: {collapse_whitespace(str(value))}")
    return "\n".join(parts) if parts else None


def coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = collapse_whitespace(str(value))
    return text or None


#: Multiplier words :func:`parse_amount` already understands.
_KNOWN_MULTIPLIERS = frozenset({"cr", "crs", "crore", "crores", "lakh", "lakhs", "lac", "lacs"})

#: The workbook writes multipliers flush against the digits ("2.91CR"), and
#: parse_amount's crore/lakh patterns are word-bounded, so they miss it. Insert
#: the separator rather than loosening the shared pattern, which the tender
#: import also depends on.
_TIGHT_MULTIPLIER = re.compile(r"(?<=\d)(?=(?:cr(?:ore)?s?|la(?:kh|c)s?)\b)", re.IGNORECASE)

#: A short alphabetic token sitting immediately after the number, on the same
#: line. "94 Lakh" and "2.91CR" match here and are understood; "61 LC" matches
#: and is not.
_ADJACENT_SUFFIX = re.compile(r"\d[\d,. ]*?\s?([A-Za-z]{1,6})")


def coerce_amount(value: Any) -> Decimal | None:
    """Exact decimal, or None. Never a float, and never a guessed magnitude.

    An unrecognised unit suffix returns ``None`` rather than the bare number.
    The workbook carries ``61LC`` alongside ``1.13CR``; ``LC`` is very probably
    lakh, but "probably" is a factor of 100,000 on a figure the eligibility
    engine treats as evidence of capability. An absent work value is visible —
    the import reports it, and stage B skips the project — whereas a value wrong
    by five orders of magnitude is invisible and scores real tenders.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value >= 0 else None
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value) if value >= 0 else None
    # A float can only arrive from openpyxl reading a numeric cell. Round-trip it
    # through repr so the Decimal is built from the shown digits rather than the
    # binary expansion, keeping money exact from here on.
    if isinstance(value, float):
        return parse_amount(repr(value))

    text = str(value)
    # Junk after a newline is ignored; only the first line carries the amount.
    lines = str(text).splitlines()
    head = lines[0] if lines else ""
    suffix = _ADJACENT_SUFFIX.match(head.strip())
    if suffix is not None and suffix.group(1).lower() not in _KNOWN_MULTIPLIERS:
        return None
    return parse_amount(_TIGHT_MULTIPLIER.sub(" ", head))


def coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(str(value))


def split_certificate(value: Any) -> tuple[date | None, str | None]:
    """Return ``(date, note)`` for a completion-certificate cell.

    A parseable date yields ``(date, None)``. Anything else non-blank — ``Running``
    being the one seen in the real workbook — yields ``(None, verbatim)`` so the
    distinction between "no certificate recorded" and "work still running"
    survives the import. It is capped to the column width the entity allows.
    """
    if value is None:
        return None, None
    parsed = coerce_date(value)
    if parsed is not None:
        return parsed, None
    text = coerce_text(value)
    return None, text[:64] if text else None


def parse_project_rows(content: bytes) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield ``(row_number, record)`` for each non-blank portfolio row."""
    return parse_rows(content, PROJECT_HEADER_ALIASES, build_description)
