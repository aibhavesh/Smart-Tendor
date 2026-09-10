"""TenderMetadata — the ten extracted fields, each with a confidence score.

Absent values are :data:`UNKNOWN` (never guessed). ``raw_text`` is retained so a
field can be re-parsed or audited without re-downloading the source document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tender_intel.domain.value_objects.extracted_field import ExtractedField

# The ten metadata fields extracted from a tender document.
METADATA_FIELDS: tuple[str, ...] = (
    "work_name",
    "estimated_value",
    "emd_amount",
    "tender_fee",
    "closing_date",
    "completion_period",
    "location",
    "department",
    "eligibility_criteria",
    "scope_of_work",
)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class TenderMetadata:
    tender_id: UUID
    work_name: ExtractedField[str] = field(default_factory=ExtractedField.unknown)
    estimated_value: ExtractedField[Decimal] = field(default_factory=ExtractedField.unknown)
    emd_amount: ExtractedField[Decimal] = field(default_factory=ExtractedField.unknown)
    tender_fee: ExtractedField[Decimal] = field(default_factory=ExtractedField.unknown)
    closing_date: ExtractedField[date] = field(default_factory=ExtractedField.unknown)
    completion_period: ExtractedField[str] = field(default_factory=ExtractedField.unknown)
    location: ExtractedField[str] = field(default_factory=ExtractedField.unknown)
    department: ExtractedField[str] = field(default_factory=ExtractedField.unknown)
    eligibility_criteria: ExtractedField[str] = field(default_factory=ExtractedField.unknown)
    scope_of_work: ExtractedField[str] = field(default_factory=ExtractedField.unknown)
    raw_text: str = ""
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def touch(self) -> None:
        """Mark the record as changed *now*.

        The staleness rule compares this against a verdict's ``created_at`` to
        decide whether a decision has been superseded, so the bump has to be an
        explicit act on the same (Python, microsecond-precision) clock as the
        review record. Leaving it to the ORM's ``onupdate`` would source it from
        the database server instead — second-granular on SQLite, transaction-start
        time on PostgreSQL — and a correction could then read as *older* than the
        verdict it invalidated.
        """
        self.updated_at = _now()

    def field_confidences(self) -> dict[str, float]:
        return {name: getattr(self, name).confidence for name in METADATA_FIELDS}

    @property
    def known_field_count(self) -> int:
        return sum(1 for name in METADATA_FIELDS if getattr(self, name).is_known)
