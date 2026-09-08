"""Human-review request/response schemas.

Two request shapes, because there are two acts. A correction cannot carry a
verdict and a verdict cannot be submitted without one — that distinction is
enforced by which endpoint you call, never by inspecting a payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from tender_intel.domain.entities import TenderReview
from tender_intel.domain.enums.review import ReviewKind, ReviewVerdict
from tender_intel.domain.services.staleness import verdict_is_stale


class CorrectionCreateRequest(BaseModel):
    """{metadata_field: corrected_value_as_string}. At least one entry."""

    corrections: dict[str, str] = Field(min_length=1)
    comments: str | None = Field(default=None, max_length=4000)


class VerdictCreateRequest(BaseModel):
    verdict: ReviewVerdict
    comments: str | None = Field(default=None, max_length=4000)
    # A verdict may correct fields on its way through; applied before the
    # tender transitions.
    corrections: dict[str, str] = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    id: UUID
    tender_id: UUID
    reviewer_id: UUID
    kind: ReviewKind
    #: NULL on a correction.
    verdict: ReviewVerdict | None
    comments: str | None
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    created_at: datetime
    #: True when metadata was corrected after this verdict was recorded, so the
    #: decision rests on evidence that has since changed. Always false for a
    #: correction — a correction is not a decision and cannot be superseded.
    is_stale: bool

    @classmethod
    def from_entity(
        cls, r: TenderReview, *, metadata_updated_at: datetime | None = None
    ) -> ReviewResponse:
        return cls(
            id=r.id,
            tender_id=r.tender_id,
            reviewer_id=r.reviewer_id,
            kind=r.kind,
            verdict=r.verdict,
            comments=r.comments,
            before_snapshot=r.before_snapshot,
            after_snapshot=r.after_snapshot,
            created_at=r.created_at,
            is_stale=(r.is_verdict and verdict_is_stale(r.created_at, metadata_updated_at)),
        )
