"""Bulk tender retirement contracts.

The preview and the execution return the same shape for the selection, so the
confirmation dialog can show what will happen and what did happen without
switching layouts.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from tender_intel.application.services.retirement_service import (
    RetirementOutcome,
    RetirementPlan,
)
from tender_intel.domain.retirement import RetirementCandidate


class RetirementCandidateResponse(BaseModel):
    tender_id: UUID
    tender_number: str
    title: str
    status: str
    closing_date: date | None
    documents_to_purge: int
    bytes_to_reclaim: int
    retirable: bool
    #: Set when this tender is in the date window but will not be retired.
    skip_reason: str | None

    @classmethod
    def from_dto(cls, c: RetirementCandidate) -> RetirementCandidateResponse:
        return cls(
            tender_id=c.tender_id,
            tender_number=c.tender_number,
            title=c.title,
            status=c.status.value,
            closing_date=c.closing_date,
            documents_to_purge=c.documents_to_purge,
            bytes_to_reclaim=c.bytes_to_reclaim,
            retirable=c.retirable,
            skip_reason=c.skip.value if c.skip is not None else None,
        )


class RetirementPreviewResponse(BaseModel):
    """What the operation would do. Nothing has been changed."""

    cutoff: date
    #: The timezone the cutoff was computed in, stated so "past" is unambiguous.
    timezone: str
    retirable_count: int
    skipped_count: int
    documents_to_purge: int
    bytes_to_reclaim: int
    #: Tenders no date filter can reach, because their closing date is unknown.
    #: Reported so they are visibly excluded rather than quietly missed.
    unknown_closing_date: int
    #: True when more tenders matched than one operation may take.
    truncated: bool
    candidates: list[RetirementCandidateResponse]

    @classmethod
    def from_dto(cls, plan: RetirementPlan) -> RetirementPreviewResponse:
        return cls(
            cutoff=plan.cutoff,
            timezone=plan.timezone_name,
            retirable_count=len(plan.retirable),
            skipped_count=len(plan.skipped),
            documents_to_purge=plan.documents_to_purge,
            bytes_to_reclaim=plan.bytes_to_reclaim,
            unknown_closing_date=plan.unknown_closing_date,
            truncated=plan.truncated,
            candidates=[RetirementCandidateResponse.from_dto(c) for c in plan.candidates],
        )


class RetirementRequest(BaseModel):
    """Execute the retirement.

    ``cutoff`` defaults to today in Asia/Kolkata. ``tender_ids`` narrows the run
    to the subset the operator confirmed; ids outside the selection are ignored,
    because the selection rules are the authority rather than the caller's list.
    """

    cutoff: date | None = None
    tender_ids: list[UUID] | None = Field(default=None, max_length=200)


class RetirementResultResponse(BaseModel):
    cutoff: date
    timezone: str
    tenders_archived: int
    documents_purged: int
    bytes_reclaimed: int
    #: Files storage refused to delete. Their rows are untouched, so a repeat run
    #: will try them again.
    failures: list[str]
    #: Stated in the response as well as the audit entry, so a caller reading only
    #: this can see that nothing was erased.
    retained: str

    @classmethod
    def from_dto(cls, outcome: RetirementOutcome) -> RetirementResultResponse:
        return cls(
            cutoff=outcome.plan.cutoff,
            timezone=outcome.plan.timezone_name,
            tenders_archived=outcome.tenders_archived,
            documents_purged=outcome.documents_purged,
            bytes_reclaimed=outcome.bytes_reclaimed,
            failures=outcome.failures,
            retained="tender row, metadata, BOQ items, reviews, eligibility result",
        )
