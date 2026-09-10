"""What makes a tender retirable, and what retirement does to it.

Retirement is storage and queue hygiene, not erasure. The stored PDF is tens of
megabytes; the tender row, its metadata and its BOQ items are a few kilobytes.
Purging the bytes reclaims essentially all of the storage and loses none of the
analytical value, so the posture is **purge the artefact, retain the record**.

Three rules decide the selection, and each exists to stop a specific mistake.

*An unknown closing date is never swept up.* ``tenders.closing_date`` is nullable
and, in practice, null on tenders whose closing date was never extracted. A null
is not a past date, it is an absent one, and the two must not be conflated. Such
tenders are counted and named as excluded rather than silently skipped, because
"silently skipped" and "silently deleted" look identical afterwards.

*Nothing is purged before extraction has run.* The bytes are the only copy of a
document until ``PARSED``. Requiring ``REVIEWED`` would be far too strict — most
expired tenders were never decided at all, which is exactly why they clutter the
queue — so the bar is that extraction has happened, not that a human has.

*The cutoff is a date in a stated timezone.* ``closing_date`` is date-only, so
"past" is meaningless without saying past *where*. These are Indian tenders and
the business day is what matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from uuid import UUID

from tender_intel.domain.entities import Tender
from tender_intel.domain.enums.tender_status import TenderStatus

#: Asia/Kolkata. Fixed offset rather than a zoneinfo lookup: India has observed
#: UTC+05:30 without daylight saving since 1945, and a fixed offset needs no tz
#: database present in the container.
IST = timezone(timedelta(hours=5, minutes=30), "IST")

#: Statuses whose documents have already been through extraction, so purging the
#: stored bytes cannot destroy the only copy of unextracted data.
PURGEABLE_STATUSES: frozenset[TenderStatus] = frozenset(
    {TenderStatus.PARSED, TenderStatus.ANALYZED, TenderStatus.REVIEWED}
)


class SkipReason(StrEnum):
    """Why a tender in the date window is not retirable."""

    UNKNOWN_CLOSING_DATE = "unknown_closing_date"
    NOT_YET_PARSED = "not_yet_parsed"
    ALREADY_ARCHIVED = "already_archived"


def default_cutoff(now: datetime | None = None, *, tz: tzinfo = IST) -> date:
    """The first day that is *not* expired: today, in the given timezone.

    A tender closing today is still open for business today, so the comparison
    against this cutoff is strictly less-than.
    """
    moment = now.astimezone(tz) if now is not None else datetime.now(tz)
    return moment.date()


def is_expired(tender: Tender, cutoff: date) -> bool:
    """True only for a tender with a known closing date strictly before cutoff.

    A null closing date returns False. It is an absent date, not a past one.
    """
    if tender.closing_date is None:
        return False
    return tender.closing_date < cutoff


def skip_reason(tender: Tender, cutoff: date) -> SkipReason | None:
    """Why this tender cannot be retired, or None when it can."""
    if tender.closing_date is None:
        return SkipReason.UNKNOWN_CLOSING_DATE
    if tender.status is TenderStatus.ARCHIVED:
        return SkipReason.ALREADY_ARCHIVED
    if tender.status not in PURGEABLE_STATUSES:
        return SkipReason.NOT_YET_PARSED
    return None


@dataclass(frozen=True, slots=True)
class RetirementCandidate:
    """One tender the operation would touch, and what it would do to it."""

    tender_id: UUID
    tender_number: str
    title: str
    status: TenderStatus
    closing_date: date | None
    #: Documents holding bytes that would be deleted.
    documents_to_purge: int
    #: Bytes those documents occupy, when the size was recorded.
    bytes_to_reclaim: int
    skip: SkipReason | None = None

    @property
    def retirable(self) -> bool:
        return self.skip is None
