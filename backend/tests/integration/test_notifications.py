"""Email notification of eligible tenders.

No real address appears anywhere in this file: every recipient is produced by
seeding a user at a role and letting the service resolve it, which is the
behaviour under test. No mail leaves the process — the sender is a stub.

The three things the feature has to get right have their own sections:
idempotency, failure isolation, and auditability.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from tender_intel.application.services.notification_service import (
    RECIPIENT_ROLE,
    EligibilityNotificationService,
)
from tender_intel.domain.entities import Tender, TenderEligibility
from tender_intel.domain.enums.eligibility import EligibilityStatus
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.eligibility_repo import (
    SqlAlchemyEligibilityNotificationRepository,
    SqlAlchemyTenderEligibilityRepository,
)
from tender_intel.infrastructure.repositories.tender_repo import SqlAlchemyTenderRepository
from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository

from .helpers import seed_user

# A domain that cannot receive mail, used only where a test needs an address
# shape rather than a destination.
TEST_DOMAIN = "example.invalid"


class StubSender:
    """Captures what would have been sent. Nothing leaves the process."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._fail_with = fail_with

    async def send(self, *, to, subject, text_body, html_body=None) -> None:
        if self._fail_with is not None:
            raise self._fail_with
        self.calls.append({"to": list(to), "subject": subject, "text_body": text_body})


async def make_service(app, session, sender, *, enabled: bool = True):
    return EligibilityNotificationService(
        tenders=SqlAlchemyTenderRepository(session),
        results=SqlAlchemyTenderEligibilityRepository(session),
        notifications=SqlAlchemyEligibilityNotificationRepository(session),
        users=SqlAlchemyUserRepository(session),
        sender=sender,
        audits=SqlAlchemyAuditLogRepository(session),
        enabled=enabled,
    )


async def seed_screened(
    app,
    *,
    number: str,
    status: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    fingerprint: str = "fp-1",
) -> Tender:
    factory = app.state.test_session_factory
    async with factory() as session:
        tenders = SqlAlchemyTenderRepository(session)
        tender = await tenders.add(
            Tender(
                tender_number=number,
                title=f"Work {number}",
                department="Signalling",
                closing_date=date(2099, 1, 1),
            )
        )
        results = SqlAlchemyTenderEligibilityRepository(session)
        await results.upsert(
            TenderEligibility(tender_id=tender.id, status=status, inputs_fingerprint=fingerprint)
        )
        await session.commit()
        return tender


async def run_digest(app, sender, *, enabled: bool = True, actor_id=None):
    factory = app.state.test_session_factory
    async with factory() as session:
        service = await make_service(app, session, sender, enabled=enabled)
        outcome = await service.send_digest(actor_id=actor_id or uuid4())
        await session.commit()
        return outcome


async def digest_audits(app):
    factory = app.state.test_session_factory
    async with factory() as session:
        page = await SqlAlchemyAuditLogRepository(session).list(PageRequest(limit=200))
        return [a for a in page.items if a.action == "eligibility.notification_digest"]


# --- recipients are resolved by role, at send time -------------------------


async def test_managers_receive_the_digest(client, app_db):
    manager = await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="T-1")
    sender = StubSender()

    outcome = await run_digest(app_db, sender)
    assert outcome.sent is True
    assert outcome.recipients == [manager.email]
    assert sender.calls[0]["to"] == [manager.email]


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPER_ADMIN])
async def test_roles_above_manager_are_excluded(client, app_db, role):
    """MANAGER means exactly MANAGER.

    The hierarchy is inclusive-upward everywhere else, so a level comparison
    would silently widen this to people who administer the system rather than
    decide on bids.
    """
    await seed_user(app_db, email=f"{role.value.lower()}@{TEST_DOMAIN}", role=role)
    await seed_screened(app_db, number="T-2")
    sender = StubSender()

    outcome = await run_digest(app_db, sender)
    assert outcome.no_recipients is True
    assert outcome.sent is False
    assert sender.calls == []


async def test_employees_are_excluded(client, app_db):
    await seed_user(app_db, email=f"e@{TEST_DOMAIN}", role=UserRole.EMPLOYEE)
    await seed_screened(app_db, number="T-3")
    assert (await run_digest(app_db, StubSender())).no_recipients is True


async def test_a_manager_among_other_roles_is_the_only_recipient(client, app_db):
    manager = await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_user(app_db, email=f"a@{TEST_DOMAIN}", role=UserRole.ADMIN)
    await seed_user(app_db, email=f"s@{TEST_DOMAIN}", role=UserRole.SUPER_ADMIN)
    await seed_user(app_db, email=f"e@{TEST_DOMAIN}", role=UserRole.EMPLOYEE)
    await seed_screened(app_db, number="T-4")

    outcome = await run_digest(app_db, StubSender())
    assert outcome.recipients == [manager.email]


async def test_a_deactivated_manager_is_not_a_recipient(client, app_db):
    """Resolved at send time, so deactivation between evaluation and send counts."""
    await seed_user(app_db, email=f"gone@{TEST_DOMAIN}", role=UserRole.MANAGER, is_active=False)
    await seed_screened(app_db, number="T-5")
    assert (await run_digest(app_db, StubSender())).no_recipients is True


async def test_the_recipient_role_is_manager():
    assert RECIPIENT_ROLE is UserRole.MANAGER


# --- the empty set fails loudly --------------------------------------------


async def test_no_manager_is_reported_rather_than_succeeding_quietly(client, app_db):
    await seed_screened(app_db, number="T-6")
    outcome = await run_digest(app_db, StubSender())
    assert outcome.no_recipients is True
    assert outcome.sent is False


async def test_an_empty_recipient_set_is_still_audited(client, app_db):
    await seed_screened(app_db, number="T-7")
    # The audit must survive: raising inside the transaction would roll it back,
    # losing the only durable record that nobody was notified.
    await run_digest(app_db, StubSender())

    entries = await digest_audits(app_db)
    assert len(entries) == 1
    assert entries[0].diff["recipient_count"] == 0
    assert entries[0].diff["sent"] is False
    assert "MANAGER" in entries[0].diff["error"]


async def test_the_endpoint_reports_409_when_nobody_holds_the_role(client, app_db):
    from .helpers import auth_headers

    headers = await auth_headers(client, app_db, email=f"admin@{TEST_DOMAIN}", role=UserRole.ADMIN)
    await seed_screened(app_db, number="T-8")
    resp = await client.post("/api/v1/notifications/eligibility/digest", headers=headers)
    assert resp.status_code == 409


# --- what the email contains ------------------------------------------------


async def test_the_body_carries_the_fields_needed_to_triage(client, app_db):
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="T-9")
    sender = StubSender()
    await run_digest(app_db, sender)

    body = sender.calls[0]["text_body"]
    assert "T-9" in body
    assert "Signalling" in body
    assert "2099-01-01" in body


async def test_indeterminate_tenders_appear_in_their_own_section(client, app_db):
    """Not eligible, but rule 1b routes them to a person.

    Often the more urgent of the two: nobody looks at them unless told.
    """
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="ELIG-1", status=EligibilityStatus.ELIGIBLE)
    await seed_screened(app_db, number="IND-1", status=EligibilityStatus.INDETERMINATE)
    sender = StubSender()
    outcome = await run_digest(app_db, sender)

    assert [t.tender_number for t in outcome.eligible] == ["ELIG-1"]
    assert [t.tender_number for t in outcome.indeterminate] == ["IND-1"]
    body = sender.calls[0]["text_body"]
    assert "ELIGIBLE" in body
    assert "NEEDS REVIEW" in body


async def test_not_eligible_tenders_are_never_sent(client, app_db):
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="NO-1", status=EligibilityStatus.NOT_ELIGIBLE)
    outcome = await run_digest(app_db, StubSender())
    assert outcome.tenders == []
    assert outcome.sent is False


# --- idempotency ------------------------------------------------------------


async def test_a_tender_is_not_re_sent_on_a_second_run(client, app_db):
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="T-10")

    first = await run_digest(app_db, StubSender())
    second_sender = StubSender()
    second = await run_digest(app_db, second_sender)

    assert first.sent is True
    assert second.sent is False
    assert second.tenders == []
    assert second_sender.calls == []


async def test_a_changed_result_notifies_again(client, app_db):
    """The fingerprint is the key, not the tender.

    Re-screening unchanged inputs is silent; a genuinely changed result is news.
    """
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    tender = await seed_screened(app_db, number="T-11", fingerprint="fp-before")
    await run_digest(app_db, StubSender())

    factory = app_db.state.test_session_factory
    async with factory() as session:
        results = SqlAlchemyTenderEligibilityRepository(session)
        await results.upsert(
            TenderEligibility(
                tender_id=tender.id,
                status=EligibilityStatus.ELIGIBLE,
                inputs_fingerprint="fp-after",
            )
        )
        await session.commit()

    again = await run_digest(app_db, StubSender())
    assert again.sent is True
    assert [t.tender_number for t in again.eligible] == ["T-11"]


# --- failure isolation ------------------------------------------------------


async def test_a_send_failure_leaves_the_tender_unnotified(client, app_db):
    """A failed send must not consume the notification.

    It also cannot touch the eligibility result: by the time the digest runs the
    evaluation is long committed, so isolation here is structural.
    """
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    tender = await seed_screened(app_db, number="T-12")

    failed = await run_digest(app_db, StubSender(fail_with=OSError("smtp down")))
    assert failed.sent is False
    assert "smtp down" in (failed.error or "")

    # The eligibility result is untouched.
    factory = app_db.state.test_session_factory
    async with factory() as session:
        record = await SqlAlchemyTenderEligibilityRepository(session).get(tender.id)
    assert record is not None
    assert record.status is EligibilityStatus.ELIGIBLE

    # And the next run retries it.
    retry = await run_digest(app_db, StubSender())
    assert retry.sent is True
    assert [t.tender_number for t in retry.eligible] == ["T-12"]


async def test_a_send_failure_is_audited(client, app_db):
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="T-13")
    await run_digest(app_db, StubSender(fail_with=OSError("smtp down")))

    entries = await digest_audits(app_db)
    assert entries[0].diff["sent"] is False
    assert "smtp down" in entries[0].diff["error"]


async def test_disabling_notifications_sends_nothing(client, app_db):
    await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="T-14")
    sender = StubSender()
    outcome = await run_digest(app_db, sender, enabled=False)
    assert outcome.sent is False
    assert sender.calls == []


# --- auditability -----------------------------------------------------------


async def test_the_audit_records_who_was_resolved_not_just_that_a_send_happened(client, app_db):
    """Six months from now the question is who received a given tender."""
    manager = await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    await seed_screened(app_db, number="T-15")
    await run_digest(app_db, StubSender())

    entries = await digest_audits(app_db)
    assert len(entries) == 1
    diff = entries[0].diff
    assert diff["recipients"] == [manager.email]
    assert diff["recipient_role"] == "MANAGER"
    assert diff["eligible"] == ["T-15"]
    assert diff["sent"] is True


async def test_the_recipient_list_is_stored_on_the_ledger_entry(client, app_db):
    manager = await seed_user(app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    tender = await seed_screened(app_db, number="T-16")
    await run_digest(app_db, StubSender())

    factory = app_db.state.test_session_factory
    async with factory() as session:
        repo = SqlAlchemyEligibilityNotificationRepository(session)
        assert await repo.was_notified(tender.id, "fp-1") is True

    entries = await digest_audits(app_db)
    assert manager.email in entries[0].diff["recipients"]


# --- access -----------------------------------------------------------------


async def test_the_endpoints_require_admin(client, app_db):
    from .helpers import auth_headers

    headers = await auth_headers(client, app_db, email=f"m@{TEST_DOMAIN}", role=UserRole.MANAGER)
    assert (
        await client.get("/api/v1/notifications/eligibility/pending", headers=headers)
    ).status_code == 403
    assert (
        await client.post("/api/v1/notifications/eligibility/digest", headers=headers)
    ).status_code == 403


async def test_anonymous_is_refused(client, app_db):
    assert (await client.get("/api/v1/notifications/eligibility/pending")).status_code == 401
