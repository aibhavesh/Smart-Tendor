"""Eligibility notification contracts."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from tender_intel.application.services.notification_service import (
    DigestOutcome,
    NotifiableTender,
)


class NotifiableTenderResponse(BaseModel):
    tender_id: UUID
    tender_number: str
    title: str
    department: str | None
    estimated_value: Decimal | None
    closing_date: str | None
    status: str
    rule_satisfied: str | None

    @classmethod
    def from_dto(cls, t: NotifiableTender) -> NotifiableTenderResponse:
        return cls(
            tender_id=t.tender_id,
            tender_number=t.tender_number,
            title=t.title,
            department=t.department,
            estimated_value=t.estimated_value,
            closing_date=t.closing_date,
            status=t.status.value,
            rule_satisfied=t.rule_satisfied,
        )


class PendingDigestResponse(BaseModel):
    """What the next digest would contain. Nothing has been sent."""

    #: Addresses resolved live from the user table, by role.
    recipients: list[str]
    recipient_count: int
    eligible: list[NotifiableTenderResponse]
    #: Not eligible, but routed to a person under rule 1b. Often the more urgent
    #: of the two, because nobody looks at them unless told.
    indeterminate: list[NotifiableTenderResponse]

    @classmethod
    def build(
        cls,
        eligible: list[NotifiableTender],
        indeterminate: list[NotifiableTender],
        recipients: list[str],
    ) -> PendingDigestResponse:
        return cls(
            recipients=recipients,
            recipient_count=len(recipients),
            eligible=[NotifiableTenderResponse.from_dto(t) for t in eligible],
            indeterminate=[NotifiableTenderResponse.from_dto(t) for t in indeterminate],
        )


class DigestResultResponse(BaseModel):
    sent: bool
    recipients: list[str]
    recipient_count: int
    eligible_count: int
    indeterminate_count: int
    #: Set when the send failed. The eligibility results are untouched and the
    #: next run will retry them.
    error: str | None

    @classmethod
    def from_dto(cls, outcome: DigestOutcome) -> DigestResultResponse:
        return cls(
            sent=outcome.sent,
            recipients=outcome.recipients,
            recipient_count=len(outcome.recipients),
            eligible_count=len(outcome.eligible),
            indeterminate_count=len(outcome.indeterminate),
            error=outcome.error,
        )
