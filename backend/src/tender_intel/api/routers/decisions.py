"""Decision routes: run the engines and read the recommendation (FR-300..FR-326).

Both responses carry ``verdict_is_stale``. The recommendation itself is always
current — it is recomputed here from live metadata — but the *recorded* verdict
may predate a correction, and a manager reading this screen needs to know that
before trusting the decision already on file. Composing ReviewService here keeps
that lookup out of DecisionService, so the engines stay untouched.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from tender_intel.api.dependencies.auth import get_current_user, require_role
from tender_intel.api.dependencies.services import get_decision_service, get_review_service
from tender_intel.api.schemas.decision import DecisionResponse
from tender_intel.application.services.decision_service import DecisionService
from tender_intel.application.services.review_service import ReviewService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole

router = APIRouter(prefix="/tenders/{tender_id}", tags=["decision"])


@router.post("/analyze", response_model=DecisionResponse)
async def analyze(
    tender_id: UUID,
    service: DecisionService = Depends(get_decision_service),
    reviews: ReviewService = Depends(get_review_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> DecisionResponse:
    result = await service.analyze(tender_id, actor_id=user.id)
    return DecisionResponse.from_result(
        tender_id, result, verdict_is_stale=await reviews.verdict_is_stale(tender_id)
    )


@router.get("/recommendation", response_model=DecisionResponse)
async def get_recommendation(
    tender_id: UUID,
    service: DecisionService = Depends(get_decision_service),
    reviews: ReviewService = Depends(get_review_service),
    _: User = Depends(get_current_user),
) -> DecisionResponse:
    # Deterministic recompute (no state change).
    result = await service.compute(tender_id)
    return DecisionResponse.from_result(
        tender_id, result, verdict_is_stale=await reviews.verdict_is_stale(tender_id)
    )
