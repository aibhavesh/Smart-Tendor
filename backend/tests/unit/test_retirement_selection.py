"""What counts as expired, and what must never be swept up.

The selection rules are the destructive part of tender retirement, so they are
pinned here independently of the service that executes them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from tender_intel.domain.entities import Tender
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.retirement import (
    IST,
    PURGEABLE_STATUSES,
    SkipReason,
    default_cutoff,
    is_expired,
    skip_reason,
)

pytestmark = pytest.mark.regression

CUTOFF = date(2026, 9, 10)


def tender(
    *,
    closing: date | None = date(2026, 1, 1),
    status: TenderStatus = TenderStatus.PARSED,
) -> Tender:
    t = Tender(tender_number="T-1", title="Work", closing_date=closing)
    t.status = status
    return t


# --- the null closing date, which must never be treated as past ---


def test_an_unknown_closing_date_is_not_expired():
    """An absent date is not a past one.

    This is the whole hazard: a filter that treats null as past would purge the
    documents of every tender whose closing date was never extracted.
    """
    assert is_expired(tender(closing=None), CUTOFF) is False


def test_an_unknown_closing_date_is_reported_as_its_own_reason():
    assert skip_reason(tender(closing=None), CUTOFF) is SkipReason.UNKNOWN_CLOSING_DATE


def test_an_unknown_closing_date_outranks_every_other_reason():
    # Even a REGISTERED tender with no date reports the date, because that is
    # the reason a human has to resolve before it can ever be considered.
    unparsed = tender(closing=None, status=TenderStatus.REGISTERED)
    assert skip_reason(unparsed, CUTOFF) is SkipReason.UNKNOWN_CLOSING_DATE


# --- the cutoff boundary ---


def test_a_tender_closing_before_the_cutoff_is_expired():
    assert is_expired(tender(closing=date(2026, 9, 9)), CUTOFF) is True


def test_a_tender_closing_on_the_cutoff_is_not_expired():
    # Still open for business today.
    assert is_expired(tender(closing=CUTOFF), CUTOFF) is False


def test_a_tender_closing_after_the_cutoff_is_not_expired():
    assert is_expired(tender(closing=date(2026, 9, 11)), CUTOFF) is False


# --- the timezone the cutoff is computed in ---


def test_the_cutoff_is_todays_date_in_india():
    # 19:00 UTC is already the next day in IST (+05:30). The cutoff must follow
    # the Indian business day, not UTC.
    evening_utc = datetime(2026, 9, 10, 19, 0, tzinfo=UTC)
    assert default_cutoff(evening_utc) == date(2026, 9, 11)


def test_the_cutoff_matches_utc_during_the_indian_working_day():
    midday_utc = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    assert default_cutoff(midday_utc) == date(2026, 9, 10)


def test_ist_is_five_and_a_half_hours_ahead():
    assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)


# --- the extraction bar ---


@pytest.mark.parametrize("status", sorted(PURGEABLE_STATUSES, key=lambda s: s.value))
def test_a_tender_past_extraction_is_retirable(status):
    assert skip_reason(tender(status=status), CUTOFF) is None


@pytest.mark.parametrize("status", [TenderStatus.REGISTERED, TenderStatus.DOWNLOADED])
def test_a_tender_before_extraction_is_refused(status):
    """Purging here would destroy the only copy of never-extracted data."""
    assert skip_reason(tender(status=status), CUTOFF) is SkipReason.NOT_YET_PARSED


def test_an_already_archived_tender_is_skipped():
    assert skip_reason(tender(status=TenderStatus.ARCHIVED), CUTOFF) is SkipReason.ALREADY_ARCHIVED


def test_the_purgeable_set_excludes_everything_before_parsed():
    assert TenderStatus.REGISTERED not in PURGEABLE_STATUSES
    assert TenderStatus.DOWNLOADED not in PURGEABLE_STATUSES
    assert TenderStatus.ARCHIVED not in PURGEABLE_STATUSES


def test_a_reviewed_tender_is_still_retirable():
    """Retirement keeps the record, so a decided tender is safe to retire.

    Requiring a verdict would be the wrong bar in the other direction: most
    expired tenders were never decided, which is why they clutter the queue.
    """
    assert skip_reason(tender(status=TenderStatus.REVIEWED), CUTOFF) is None
