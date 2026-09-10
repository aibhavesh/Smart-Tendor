"""Email notification of eligible tenders.

Decisions, one line each.

*A digest, not one email per tender.* A bulk import or a batch of parses fires
many evaluations at once, and a message per tender would bury the signal in the
volume it created.

*Queued, not transactional.* The digest is a separate call that reads recorded
eligibility results. A send therefore cannot fail or roll back an evaluation,
because by the time it runs the evaluation is already committed. Failure
isolation here is structural rather than defensive.

*INDETERMINATE tenders are included, in their own section.* They are not
eligible, but under rule 1b they route to a person, and an undecidable tender is
often more urgent than a clean pass — it is the one nobody will look at unless
told.

*The email carries number, department, value, closing date and which rule branch
was satisfied*, which is enough to triage without opening the app.

Recipients are resolved by role at send time and never configured as addresses.
The set is every **active** user holding exactly ``MANAGER``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from tender_intel.domain.entities import (
    AuditLog,
    EligibilityNotification,
    Tender,
    TenderEligibility,
    User,
)
from tender_intel.domain.enums.eligibility import EligibilityStatus
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.interfaces.providers import EmailSender
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    EligibilityNotificationRepository,
    TenderEligibilityRepository,
    TenderRepository,
    UserRepository,
)
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)

#: The recipient role. Exactly this role, never "this level or above" — see
#: :meth:`EligibilityNotificationService.resolve_recipients`.
RECIPIENT_ROLE = UserRole.MANAGER

#: Statuses worth telling somebody about.
NOTIFIABLE: frozenset[EligibilityStatus] = frozenset(
    {EligibilityStatus.ELIGIBLE, EligibilityStatus.INDETERMINATE}
)


class NoRecipientsError(RuntimeError):
    """Nobody holds the recipient role, so there is nobody to notify.

    Raised by the API layer, not by the service: the service records the gap
    and audits it first, because raising inside the transaction would roll the
    audit entry back and lose the only durable trace of it.
    """


@dataclass(frozen=True, slots=True)
class NotifiableTender:
    """One tender the digest would report."""

    tender_id: UUID
    tender_number: str
    title: str
    department: str | None
    estimated_value: Decimal | None
    closing_date: str | None
    status: EligibilityStatus
    #: Which similar-work rule branch was satisfied, when one was.
    rule_satisfied: str | None
    fingerprint: str


@dataclass(slots=True)
class DigestOutcome:
    """What a digest run did."""

    recipients: list[str] = field(default_factory=list)
    eligible: list[NotifiableTender] = field(default_factory=list)
    indeterminate: list[NotifiableTender] = field(default_factory=list)
    sent: bool = False
    #: True when nobody holds the recipient role. Distinct from a delivery
    #: failure: there is nobody to deliver to, which is a configuration gap
    #: rather than a transient error.
    no_recipients: bool = False
    #: Set when the send failed. The evaluation is untouched either way.
    error: str | None = None

    @property
    def tenders(self) -> list[NotifiableTender]:
        return self.eligible + self.indeterminate


class EligibilityNotificationService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        results: TenderEligibilityRepository,
        notifications: EligibilityNotificationRepository,
        users: UserRepository,
        sender: EmailSender,
        audits: AuditLogRepository,
        enabled: bool = True,
    ) -> None:
        self._tenders = tenders
        self._results = results
        self._notifications = notifications
        self._users = users
        self._sender = sender
        self._audits = audits
        self._enabled = enabled

    # --- recipients ---------------------------------------------------------

    async def resolve_recipients(self) -> list[User]:
        """Every active user holding exactly MANAGER, resolved now.

        Never cached. A role granted this morning takes effect this afternoon,
        and a role revoked this morning takes effect immediately — which is the
        whole reason the set is not configuration.

        Exact role equality, not a level comparison. ADMIN sits at 40 and
        SUPER_ADMIN at 50, both above MANAGER's 30, so any ``>=`` here would
        silently widen the audience to people who administer the system rather
        than decide on bids.
        """
        users = await self._users.list_active_with_exact_role(RECIPIENT_ROLE)
        return [u for u in users if u.is_active and _usable_email(u.email)]

    # --- the digest ---------------------------------------------------------

    async def collect(self) -> tuple[list[NotifiableTender], list[NotifiableTender]]:
        """Recorded results not yet notified, split by status."""
        eligible: list[NotifiableTender] = []
        indeterminate: list[NotifiableTender] = []

        page = await self._tenders.list(PageRequest(limit=MAX_LIMIT))
        for tender in page.items:
            record = await self._results.get(tender.id)
            if record is None or record.status not in NOTIFIABLE:
                continue
            if await self._notifications.was_notified(tender.id, record.inputs_fingerprint):
                continue
            item = _to_notifiable(tender, record)
            if record.status is EligibilityStatus.ELIGIBLE:
                eligible.append(item)
            else:
                indeterminate.append(item)
        return eligible, indeterminate

    async def send_digest(self, *, actor_id: UUID | None = None) -> DigestOutcome:
        """Send one digest covering every not-yet-notified result.

        Never raises. Two failure modes are reported on the outcome and audited:
        ``no_recipients`` when nobody holds the recipient role, and ``error``
        when delivery failed. Either way the tenders stay unnotified, so the
        next run retries them.
        """
        outcome = DigestOutcome()
        if not self._enabled:
            outcome.error = "notifications are disabled by configuration"
            await self._audit(outcome, actor_id)
            return outcome

        eligible, indeterminate = await self.collect()
        outcome.eligible = eligible
        outcome.indeterminate = indeterminate

        recipients = await self.resolve_recipients()
        outcome.recipients = [u.email for u in recipients]

        if not recipients:
            # Loud, but not by raising. Raising here would roll the audit entry
            # back with the transaction, losing the very record that makes the
            # gap visible later. So it is logged at ERROR, recorded on the
            # outcome, and audited; the API turns this into a 409.
            _log.error(
                "notification.no_recipients",
                role=RECIPIENT_ROLE.value,
                pending_tenders=len(outcome.tenders),
            )
            outcome.no_recipients = True
            outcome.error = f"no active user holds {RECIPIENT_ROLE.value}"
            await self._audit(outcome, actor_id)
            return outcome

        if not outcome.tenders:
            outcome.error = None
            await self._audit(outcome, actor_id)
            return outcome

        subject = _subject(eligible, indeterminate)
        try:
            await self._sender.send(
                to=outcome.recipients,
                subject=subject,
                text_body=_body(eligible, indeterminate),
            )
        except Exception as exc:
            # A failed send must never fail the evaluation. It cannot here — the
            # evaluation is long committed — so the only job is to record it and
            # leave the tenders unnotified for the next run.
            _log.warning("notification.send_failed", error=str(exc))
            outcome.error = str(exc)
            await self._audit(outcome, actor_id)
            return outcome

        outcome.sent = True
        for item in outcome.tenders:
            await self._notifications.add(
                EligibilityNotification(
                    tender_id=item.tender_id,
                    inputs_fingerprint=item.fingerprint,
                    status=item.status,
                    recipients=list(outcome.recipients),
                )
            )
        await self._audit(outcome, actor_id)
        return outcome

    # --- audit --------------------------------------------------------------

    async def _audit(self, outcome: DigestOutcome, actor_id: UUID | None) -> None:
        """Record who was resolved, not merely that a send happened.

        The recipient set changes as roles change, so six months from now the
        question is who actually received a given tender.
        """
        await self._audits.add(
            AuditLog(
                action="eligibility.notification_digest",
                entity_type="TenderEligibility",
                entity_id=None,
                actor_id=actor_id,
                diff={
                    "recipient_role": RECIPIENT_ROLE.value,
                    "recipients": outcome.recipients,
                    "recipient_count": len(outcome.recipients),
                    "eligible": [t.tender_number for t in outcome.eligible],
                    "indeterminate": [t.tender_number for t in outcome.indeterminate],
                    "tender_count": len(outcome.tenders),
                    "sent": outcome.sent,
                    "error": outcome.error,
                },
            )
        )


def _usable_email(email: str | None) -> bool:
    return bool(email and "@" in email)


def _to_notifiable(tender: Tender, record: TenderEligibility) -> NotifiableTender:
    return NotifiableTender(
        tender_id=tender.id,
        tender_number=tender.tender_number,
        title=tender.title,
        department=tender.department,
        estimated_value=tender.estimated_value,
        closing_date=tender.closing_date.isoformat() if tender.closing_date else None,
        status=record.status,
        rule_satisfied=record.rule_satisfied.value if record.rule_satisfied else None,
        fingerprint=record.inputs_fingerprint,
    )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _subject(eligible: list[NotifiableTender], indeterminate: list[NotifiableTender]) -> str:
    if eligible and indeterminate:
        return f"{_plural(len(eligible), 'eligible tender')}, {len(indeterminate)} needing review"
    if eligible:
        return _plural(len(eligible), "eligible tender")
    return f"{_plural(len(indeterminate), 'tender')} needing review"


def _line(t: NotifiableTender) -> str:
    value = f"{t.estimated_value:,.2f}" if t.estimated_value is not None else "unknown"
    parts = [
        f"  {t.tender_number} — {t.title}",
        f"    department: {t.department or 'unknown'}",
        f"    value: {value}",
        f"    closes: {t.closing_date or 'unknown'}",
    ]
    if t.rule_satisfied:
        parts.append(f"    satisfied: {t.rule_satisfied}")
    return "\n".join(parts)


def _body(eligible: list[NotifiableTender], indeterminate: list[NotifiableTender]) -> str:
    blocks: list[str] = []
    if eligible:
        blocks.append("ELIGIBLE\n\n" + "\n\n".join(_line(t) for t in eligible))
    if indeterminate:
        blocks.append(
            "NEEDS REVIEW (the screen could not decide; these route to a person)\n\n"
            + "\n\n".join(_line(t) for t in indeterminate)
        )
    return "\n\n\n".join(blocks) + "\n"


__all__ = [
    "NOTIFIABLE",
    "RECIPIENT_ROLE",
    "DigestOutcome",
    "EligibilityNotificationService",
    "NoRecipientsError",
    "NotifiableTender",
]
