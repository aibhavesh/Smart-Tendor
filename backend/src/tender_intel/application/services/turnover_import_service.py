"""Extract reviewable certified-turnover figures from uploaded evidence files."""

from __future__ import annotations

import asyncio
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePath

from openpyxl import load_workbook

from tender_intel.domain.interfaces.providers import DocumentTextExtractor
from tender_intel.infrastructure.extraction.parsing import parse_amount
from tender_intel.infrastructure.extraction.pdf_backends import OcrPdfTextExtractor

_YEAR_RE = re.compile(
    r"(?<!\d)(?:f(?:inancial)?\.?\s*y(?:ear)?\.?\s*[:\-]? *)?"
    # The curly apostrophe alternative is deliberate: spreadsheets commonly write
    # a financial year as 2023-24 with that character rather than a straight quote,
    # and matching only the straight one silently misses those labels.
    r"(20\d{2})\s*(?:-|/|to)\s*['’]?(\d{2}|20\d{2})(?!\d)",  # noqa: RUF001
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*\d[\d,]*(?:\.\d+)?\s*(?:cr(?:ore)?s?|la(?:kh|c)s?)?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ExtractedTurnover:
    financial_year: str
    contractual_turnover: Decimal
    source_file: str


@dataclass(frozen=True, slots=True)
class TurnoverImportResult:
    records: list[ExtractedTurnover]
    warnings: list[str]


def _normalise_year(match: re.Match[str]) -> str | None:
    start = int(match.group(1))
    raw_end = match.group(2)
    end = int(raw_end) if len(raw_end) == 4 else (start // 100) * 100 + int(raw_end)
    if end != start + 1:
        return None
    return f"{start}-{str(end)[-2:]}"


def _find_years(text: str) -> list[tuple[tuple[int, int], str]]:
    years: list[tuple[tuple[int, int], str]] = []
    for match in _YEAR_RE.finditer(text):
        label = _normalise_year(match)
        if label:
            years.append((match.span(), label))
    return years


def _amount(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value >= 0 else None
    if isinstance(value, (int, float)):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return None
        return number if number >= 0 else None
    return parse_amount(str(value))


def _header_kind(value: object) -> str | None:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    if text in {"fy", "f y", "year", "financial year", "assessment year"} or (
        "financial year" in text
    ):
        return "year"
    if "turnover" in text or "annual receipts" in text:
        return "amount"
    return None


def _dedupe(records: Iterable[ExtractedTurnover]) -> list[ExtractedTurnover]:
    # A certificate can repeat a year in a heading and a summary. Keep its first
    # matching row so the review screen contains one value per financial year.
    by_year: dict[str, ExtractedTurnover] = {}
    for record in records:
        previous = by_year.get(record.financial_year)
        if previous is None:
            by_year[record.financial_year] = record
    return [by_year[year] for year in sorted(by_year, reverse=True)]


class TurnoverImportService:
    """Turns temporary upload bytes into figures that a manager can confirm.

    The source evidence is intentionally not retained: turnover records do not
    yet have a non-tender document store.  The manager reviews the extracted
    values and uses the existing audited create/update API to persist them.
    """

    def __init__(self, *, text_extractor: DocumentTextExtractor) -> None:
        self._text_extractor = text_extractor
        self._ocr_extractor = OcrPdfTextExtractor()

    async def extract(self, *, filename: str, content: bytes) -> TurnoverImportResult:
        suffix = PurePath(filename).suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            records = await asyncio.to_thread(self._extract_workbook, content, filename)
        elif suffix == ".pdf":
            records = await asyncio.to_thread(self._extract_pdf, content, filename)
        else:
            return TurnoverImportResult([], [f"{filename}: upload a PDF, XLSX, or XLSM file."])

        if records:
            return TurnoverImportResult(_dedupe(records), [])
        return TurnoverImportResult(
            [],
            [
                f"{filename}: no financial-year and turnover pairs were found. "
                "Check the source or enter the figures manually."
            ],
        )

    def _extract_workbook(self, content: bytes, filename: str) -> list[ExtractedTurnover]:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        records: list[ExtractedTurnover] = []
        try:
            for sheet in workbook.worksheets:
                rows = list(sheet.iter_rows(values_only=True))
                header: tuple[int, int] | None = None
                header_row = 0
                for header_index, row in enumerate(rows[:20]):
                    year_column = amount_column = None
                    for column_index, value in enumerate(row):
                        kind = _header_kind(value)
                        if kind == "year":
                            year_column = column_index
                        elif kind == "amount":
                            amount_column = column_index
                    if year_column is not None and amount_column is not None:
                        header = (year_column, amount_column)
                        header_row = header_index
                        break
                if header is None:
                    records.extend(self._extract_horizontal_sheet_rows(rows, filename))
                    continue
                year_column, amount_column = header
                for row in rows[header_row + 1 :]:
                    if max(year_column, amount_column) >= len(row):
                        continue
                    years = _find_years(str(row[year_column] or ""))
                    value = _amount(row[amount_column])
                    if years and value is not None:
                        records.append(ExtractedTurnover(years[0][1], value, filename))
        finally:
            workbook.close()
        return records

    def _extract_horizontal_sheet_rows(
        self, rows: list[tuple[object, ...]], filename: str
    ) -> list[ExtractedTurnover]:
        """Read a workbook table with financial years as column headings."""
        records: list[ExtractedTurnover] = []
        for row_index, row in enumerate(rows):
            years = [
                (column, matches[0][1])
                for column, value in enumerate(row)
                if (matches := _find_years(str(value or "")))
            ]
            if not years:
                continue
            for following in rows[row_index + 1 : row_index + 4]:
                values = [
                    _amount(following[column]) if column < len(following) else None
                    for column, _ in years
                ]
                if all(value is not None and value >= Decimal("1000") for value in values):
                    records.extend(
                        ExtractedTurnover(year, value, filename)
                        for (_, year), value in zip(years, values, strict=False)
                        if value is not None
                    )
                    break
        return records

    def _extract_pdf(self, content: bytes, filename: str) -> list[ExtractedTurnover]:
        text = self._text_extractor.extract_text(content)
        if not text.strip():
            text = self._ocr_extractor.extract_text(content)
        return self._extract_text_pairs(text, filename)

    def _extract_text_pairs(self, text: str, filename: str) -> list[ExtractedTurnover]:
        records: list[ExtractedTurnover] = []
        lines = text.splitlines()
        for line_number, line in enumerate(lines):
            years = _find_years(line)
            if not years:
                continue
            if len(years) > 1:
                # CA certificates commonly place all three financial years in a
                # header row, followed by their three values on the next line.
                # The year tokens themselves are numbers, so look ahead for a
                # full monetary row rather than treating the trailing "-25" as
                # a turnover value.
                values: list[Decimal] = []
                for following in lines[line_number + 1 : line_number + 4]:
                    values = self._monetary_candidates(following)
                    if len(values) >= len(years):
                        break
                if len(values) >= len(years):
                    records.extend(
                        ExtractedTurnover(year, value, filename)
                        for (_, year), value in zip(years, values, strict=False)
                    )
                continue
            for position, (_, year) in enumerate(years):
                # Prefer a monetary-looking/large number after the year, then
                # inspect the following line for table layouts split by OCR.
                tail = line[years[position][0][1] :]
                candidates = self._monetary_candidates(tail)
                if not candidates and line_number + 1 < len(text.splitlines()):
                    candidates = self._monetary_candidates(lines[line_number + 1])
                if not candidates:
                    continue
                records.append(ExtractedTurnover(year, candidates[-1], filename))
        return records

    @staticmethod
    def _monetary_candidates(text: str) -> list[Decimal]:
        """Discard years, day/month dates and note numbers from OCR output."""
        return [
            value
            for token in _NUMBER_RE.findall(text)
            if (value := _amount(token)) is not None and value >= Decimal("1000")
        ]
