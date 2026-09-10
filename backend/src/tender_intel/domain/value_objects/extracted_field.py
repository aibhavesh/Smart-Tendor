"""A per-field extracted value carrying a confidence score.

Every field produced by the extraction layer is wrapped so that downstream
consumers (decision engines, reviewers) can see *both* the value and how much
the extractor trusted it. Absent values are :data:`UNKNOWN`, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tender_intel.domain.value_objects.unknown import UNKNOWN, Maybe, is_known


@dataclass(frozen=True, slots=True)
class ExtractedField[T]:
    value: Maybe[T]
    confidence: float = 0.0  # 0.0 .. 1.0
    source: str | None = None  # e.g. "rule:emd_regex", "pdfplumber:table"

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if not is_known(self.value) and self.confidence != 0.0:
            raise ValueError("UNKNOWN fields must have confidence 0.0")

    @property
    def is_known(self) -> bool:
        return is_known(self.value)

    @classmethod
    def unknown(cls, source: str | None = None) -> ExtractedField[T]:
        return cls(value=UNKNOWN, confidence=0.0, source=source)

    @classmethod
    def known(cls, value: T, confidence: float, source: str | None = None) -> ExtractedField[T]:
        return cls(value=value, confidence=confidence, source=source)


@dataclass(frozen=True, slots=True)
class ConfidencedText:
    """Raw extracted text kept alongside structured fields for audit/re-parse."""

    text: str = ""
    fields: dict[str, ExtractedField[object]] = field(default_factory=dict)
