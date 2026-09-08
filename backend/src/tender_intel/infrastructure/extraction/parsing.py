"""Value parsers for extraction: Indian-format amounts, quantities and dates.

All return ``None`` on failure so callers can honour the UNKNOWN convention
(never guess). Amounts are exact :class:`~decimal.Decimal`.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from tender_intel.domain.value_objects.money import CRORE, LAKH

_CURRENCY_RE = re.compile(r"(?:₹|rs\.?|inr)\s*", re.IGNORECASE)
_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
_CRORE_RE = re.compile(r"\bcr(?:ore)?s?\b", re.IGNORECASE)
_LAKH_RE = re.compile(r"\bla(?:kh|c)s?\b", re.IGNORECASE)

_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
)
_DATE_TOKEN_RE = re.compile(
    r"\d{1,2}[/\-.\s][A-Za-z0-9]{1,9}[/\-.\s,]?\s?\d{2,4}"
    r"|[A-Za-z]+\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
)


def parse_amount(text: str) -> Decimal | None:
    """Parse a monetary amount, honouring crore/lakh multipliers and ₹/Rs symbols."""
    if not text:
        return None
    cleaned = _CURRENCY_RE.sub("", text).strip()
    match = _NUMBER_RE.search(cleaned)
    if not match:
        return None
    try:
        value = Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    if _CRORE_RE.search(cleaned):
        value *= CRORE
    elif _LAKH_RE.search(cleaned):
        value *= LAKH
    if value < 0:
        return None
    return value


def parse_quantity(text: str) -> Decimal | None:
    """Parse a bare numeric quantity (no currency multipliers)."""
    if not text:
        return None
    match = _NUMBER_RE.search(text.strip())
    if not match:
        return None
    try:
        value = Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    return value if value >= 0 else None


_MONTHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(month|year)", re.IGNORECASE)
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(day|week|month|year)", re.IGNORECASE)
_DAYS_PER = {"day": 1, "week": 7, "month": 30, "year": 365}


def parse_months(text: str | None) -> int | None:
    """Parse a completion period into whole months (e.g. '18 months', '2 years')."""
    if not text:
        return None
    match = _MONTHS_RE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    if match.group(2).lower().startswith("year"):
        value *= 12
    return round(value)


def parse_days(text: str | None) -> int | None:
    """Parse a completion period into whole days (e.g. '90 days', '6 months')."""
    if not text:
        return None
    match = _DURATION_RE.search(text)
    if not match:
        return None
    value = float(match.group(1)) * _DAYS_PER[match.group(2).lower()]
    return round(value)


def parse_date(text: str) -> date | None:
    if not text:
        return None
    token_match = _DATE_TOKEN_RE.search(text)
    candidate = token_match.group(0).strip() if token_match else text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None
