"""Extraction (metadata + BOQ + analytics) response schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from tender_intel.domain.entities import BOQItem, TenderMetadata
from tender_intel.domain.entities.metadata import METADATA_FIELDS
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.unknown import Maybe, is_known


def _serialise(value: Any) -> str | None:
    if not is_known(value):
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class MetadataFieldResponse(BaseModel):
    value: str | None
    confidence: float
    source: str | None
    is_known: bool

    @classmethod
    def from_field(cls, field: ExtractedField[Any]) -> MetadataFieldResponse:
        return cls(
            value=_serialise(field.value),
            confidence=field.confidence,
            source=field.source,
            is_known=field.is_known,
        )


class MetadataResponse(BaseModel):
    tender_id: UUID
    fields: dict[str, MetadataFieldResponse]
    known_field_count: int

    @classmethod
    def from_entity(cls, metadata: TenderMetadata) -> MetadataResponse:
        return cls(
            tender_id=metadata.tender_id,
            fields={
                name: MetadataFieldResponse.from_field(getattr(metadata, name))
                for name in METADATA_FIELDS
            },
            known_field_count=metadata.known_field_count,
        )


class BOQItemResponse(BaseModel):
    id: UUID
    item_number: str | None
    description: str
    unit: str | None
    quantity: str | None
    unit_rate: str | None
    amount: str | None
    category: str | None
    confidence: float

    @classmethod
    def from_entity(cls, item: BOQItem) -> BOQItemResponse:
        return cls(
            id=item.id,
            item_number=item.item_number,
            description=item.description,
            unit=item.unit,
            quantity=_maybe(item.quantity),
            unit_rate=_maybe(item.unit_rate),
            amount=_maybe(item.amount),
            category=item.category,
            confidence=item.confidence,
        )


class ExtractionResponse(BaseModel):
    tender_id: UUID
    status: str
    metadata: MetadataResponse
    boq_item_count: int


def _maybe(value: Maybe[Decimal]) -> str | None:
    return str(value) if is_known(value) else None
