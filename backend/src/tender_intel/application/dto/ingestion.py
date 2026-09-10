"""Ingestion application DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class ImportOutcome(StrEnum):
    CREATED = "created"
    SKIPPED = "skipped"  # tender number already exists
    ERROR = "error"  # malformed row


@dataclass(frozen=True, slots=True)
class RowResult:
    row: int
    tender_number: str | None
    outcome: ImportOutcome
    message: str | None = None


@dataclass(slots=True)
class BulkImportResult:
    results: list[RowResult] = field(default_factory=list)
    # Rows that carried a link and had a document queued for download.
    queued_documents: int = 0

    @property
    def created(self) -> int:
        return sum(1 for r in self.results if r.outcome is ImportOutcome.CREATED)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.outcome is ImportOutcome.SKIPPED)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.outcome is ImportOutcome.ERROR)


@dataclass(frozen=True, slots=True)
class TenderCreate:
    tender_number: str
    title: str
    description: str | None = None
    estimated_value: Decimal | None = None
    closing_date: date | None = None
    source_url: str | None = None
    department: str | None = None


@dataclass(frozen=True, slots=True)
class TenderPatch:
    title: str | None = None
    description: str | None = None
    estimated_value: Decimal | None = None
    closing_date: date | None = None
    source_url: str | None = None
    department: str | None = None
