"""Bulk retirement of expired tenders.

ADMIN throughout. Deleting stored files across many tenders is an administrative
storage action, not analyst work. ``require_role`` rather than exact roles, so
SUPER_ADMIN keeps it.

Registered under ``/api/v1`` per the current convention for new routers.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from tender_intel.api.dependencies.auth import require_role
from tender_intel.api.dependencies.services import get_retirement_service
from tender_intel.api.schemas.retirement import (
    RetirementPreviewResponse,
    RetirementRequest,
    RetirementResultResponse,
)
from tender_intel.application.services.retirement_service import TenderRetirementService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole

router = APIRouter(prefix="/api/v1/tenders", tags=["tenders"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/retirement/preview", response_model=RetirementPreviewResponse)
async def preview_retirement(
    service: TenderRetirementService = Depends(get_retirement_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
    cutoff: date | None = Query(
        default=None,
        description=(
            "Tenders closing strictly before this date are selected. "
            "Defaults to today in Asia/Kolkata."
        ),
    ),
) -> RetirementPreviewResponse:
    """Show the selection. Writes nothing, deletes nothing.

    Tenders whose closing date is unknown are never selected — an absent date is
    not a past one — and are reported as a separate count so they are visibly
    excluded rather than quietly missed.
    """
    return RetirementPreviewResponse.from_dto(await service.preview(cutoff=cutoff))


@router.post("/retirement", response_model=RetirementResultResponse)
async def retire_tenders(
    body: RetirementRequest,
    request: Request,
    service: TenderRetirementService = Depends(get_retirement_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> RetirementResultResponse:
    """Purge the stored documents of expired tenders and archive them.

    Destroys the stored PDF bytes. Keeps the tender row, its metadata, its BOQ
    items, its reviews and its eligibility result, because those are what later
    analysis is measured against and they cost kilobytes rather than megabytes.
    """
    outcome = await service.retire(
        cutoff=body.cutoff,
        tender_ids=body.tender_ids,
        actor_id=actor.id,
        actor_role=actor.role.value,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return RetirementResultResponse.from_dto(outcome)
