"""Tender eligibility screening routes (feature spec §8).

Registered under ``/api/v1``. No other route in this API carries that prefix
today, so the surface is deliberately split — recorded as a decision rather than
a gap.

Reads sit at level 20, which is ``EMPLOYEE``. Screening a tender is analysis
work, not a decision, so it does not require the authority to decide.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from tender_intel.api.dependencies.auth import get_current_user, require_role
from tender_intel.api.dependencies.services import get_eligibility_service
from tender_intel.api.schemas.eligibility import EligibilityResponse
from tender_intel.application.services.eligibility_service import EligibilityService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole

router = APIRouter(prefix="/api/v1/tenders/{tender_id}", tags=["eligibility"])


@router.post("/eligibility", response_model=EligibilityResponse)
async def screen(
    tender_id: UUID,
    service: EligibilityService = Depends(get_eligibility_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> EligibilityResponse:
    """Evaluate the screen and record the result, replacing any previous one."""
    record = await service.screen(tender_id, actor_id=user.id)
    # Freshly computed, so it describes its own inputs by construction.
    return EligibilityResponse.from_entity(record, is_stale=False)


@router.get("/eligibility", response_model=EligibilityResponse)
async def get_eligibility(
    tender_id: UUID,
    service: EligibilityService = Depends(get_eligibility_service),
    _: User = Depends(get_current_user),
) -> EligibilityResponse:
    """Read the recorded result, reporting whether its inputs have moved."""
    record = await service.get(tender_id)
    return EligibilityResponse.from_entity(record, is_stale=await service.is_stale(tender_id))
