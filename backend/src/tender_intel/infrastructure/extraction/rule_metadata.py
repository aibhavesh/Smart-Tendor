"""Rule-based metadata extraction backend.

Scans raw document text for labelled fields (e.g. "Name of Work: ...") and
returns the ten metadata fields as :class:`ExtractedField`. Absent or
unparseable values are :data:`UNKNOWN` — the extractor never guesses.
"""

from __future__ import annotations

import re
from typing import Any

from tender_intel.domain.entities.metadata import METADATA_FIELDS
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.infrastructure.extraction.parsing import parse_amount, parse_date

# Label patterns per field. The value is captured up to end-of-line.
_LABELS: dict[str, str] = {
    "work_name": r"name of (?:the )?work|work name",
    "estimated_value": (
        r"estimated (?:cost|value|amount)|tender value|approx(?:imate)? value|value of work"
    ),
    "emd_amount": r"emd|earnest money(?: deposit)?",
    "tender_fee": r"tender fee|cost of (?:tender )?document|document fee|tender document cost",
    "closing_date": (
        r"last date(?: of submission| for submission)?|closing date|due date"
        r"|submission deadline|bid submission end date"
    ),
    "completion_period": (
        r"completion period|period of completion|time (?:of|for) completion|contract period"
    ),
    "location": r"location|place of work|work location|site",
    "department": (
        r"department|issuing authority|tender inviting authority|organis(?:z)?ation|office"
    ),
    "eligibility_criteria": r"eligibility(?: criteria)?|qualification criteria|eligible bidders",
    "scope_of_work": r"scope of work|brief scope|description of work",
}

_AMOUNT_FIELDS = frozenset({"estimated_value", "emd_amount", "tender_fee"})
_DATE_FIELDS = frozenset({"closing_date"})
_MAX_TEXT_LEN = 500

_COMPILED = {
    field: re.compile(rf"(?:{pattern})\s*[:\-]?\s*(.+)", re.IGNORECASE)
    for field, pattern in _LABELS.items()
}


class RuleBasedMetadataExtractor:
    def extract(self, text: str) -> dict[str, ExtractedField[Any]]:
        result: dict[str, ExtractedField[Any]] = {
            name: ExtractedField.unknown() for name in METADATA_FIELDS
        }
        if not text:
            return result
        for field, pattern in _COMPILED.items():
            match = pattern.search(text)
            if not match:
                continue
            raw = match.group(1).strip()
            if not raw:
                continue
            result[field] = self._to_field(field, raw)
        return result

    @staticmethod
    def _to_field(field: str, raw: str) -> ExtractedField[Any]:
        source = f"rule:{field}"
        if field in _AMOUNT_FIELDS:
            amount = parse_amount(raw)
            if amount is None:
                return ExtractedField.unknown(source=source)
            return ExtractedField.known(amount, 0.8, source=source)
        if field in _DATE_FIELDS:
            parsed = parse_date(raw)
            if parsed is None:
                return ExtractedField.unknown(source=source)
            return ExtractedField.known(parsed, 0.8, source=source)
        return ExtractedField.known(raw[:_MAX_TEXT_LEN], 0.7, source=source)
