"""Eligibility notification digest.

ADMIN, because triggering a mail-out to every manager is an operational action.
Registered under ``/api/v1`` per the current convention for new routers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from tender_intel.api.dependencies.auth import require_role
from tender_intel.api.dependencies.services import get_notification_service
from tender_intel.api.schemas.notification import (
    DigestResultResponse,
    PendingDigestResponse,
)
from tender_intel.application.services.notification_service import (
    EligibilityNotificationService,
    NoRecipientsError,
)
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/eligibility/pending", response_model=PendingDigestResponse)
async def pending_digest(
    service: EligibilityNotificationService = Depends(get_notification_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> PendingDigestResponse:
    """What the next digest would contain, and who would receive it.

    Sends nothing. The recipient set is resolved live, so an empty list here is
    the real answer, not a stale one.
    """
    eligible, indeterminate = await service.collect()
    recipients = await service.resolve_recipients()
    return PendingDigestResponse.build(eligible, indeterminate, [u.email for u in recipients])


@router.post("/eligibility/digest", response_model=DigestResultResponse)
async def send_digest(
    service: EligibilityNotificationService = Depends(get_notification_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> DigestResultResponse:
    """Send one digest of every eligibility result not yet notified.

    Returns 409 when no active user holds the recipient role: there is nobody to
    notify, and reporting success would hide that.

    A delivery failure is NOT an error here. It comes back as a 200 carrying
    ``sent: false`` and the reason, because the eligibility results are untouched
    and the next run retries them — the request did what it could.
    """
    outcome = await service.send_digest(actor_id=actor.id)
    if outcome.no_recipients:
        # The service has already logged and audited this; the audit must
        # survive, so the refusal is raised here rather than inside the
        # transaction that wrote it.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=outcome.error or str(NoRecipientsError()),
        )
    return DigestResultResponse.from_dto(outcome)
