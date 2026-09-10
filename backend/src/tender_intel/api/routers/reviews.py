"""Human review & correction routes (FR-401..FR-406).

Three gates, each on its own route — never on payload inspection inside a
handler:

* **Corrections** are an EMPLOYEE capability. Fixing a wrong EMD figure is data
  work, not a decision, and it must not require deciding.
* **The verdict** is an exact-role check against MANAGER and SUPER_ADMIN. It is
  the one capability the hierarchy must not hand upward: ADMIN outranks MANAGER
  on level but owns user administration, not the bid decision.
* **The queue** is readable by any EMPLOYEE — seeing what awaits a decision is
  not the same as making one.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from tender_intel.api.dependencies.auth import (
    get_current_user,
    require_exact_roles,
    require_role,
)
from tender_intel.api.dependencies.services import get_review_service
from tender_intel.api.schemas.common import PageResponse
from tender_intel.api.schemas.review import (
    CorrectionCreateRequest,
    ReviewResponse,
    VerdictCreateRequest,
)
from tender_intel.api.schemas.tender import TenderResponse
from tender_intel.application.services.review_service import ReviewService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest

router = APIRouter(tags=["reviews"])


@router.post(
    "/tenders/{tender_id}/corrections",
    status_code=status.HTTP_201_CREATED,
    response_model=ReviewResponse,
)
async def submit_correction(
    tender_id: UUID,
    body: CorrectionCreateRequest,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> ReviewResponse:
    review = await service.submit_correction(
        tender_id,
        reviewer_id=user.id,
        corrections=body.corrections,
        comments=body.comments,
    )
    return ReviewResponse.from_entity(review)


@router.post(
    "/tenders/{tender_id}/verdict",
    status_code=status.HTTP_201_CREATED,
    response_model=ReviewResponse,
)
async def submit_verdict(
    tender_id: UUID,
    body: VerdictCreateRequest,
    service: ReviewService = Depends(get_review_service),
    user: User = Depends(require_exact_roles(UserRole.MANAGER, UserRole.SUPER_ADMIN)),
) -> ReviewResponse:
    review = await service.submit_verdict(
        tender_id,
        reviewer_id=user.id,
        verdict=body.verdict,
        comments=body.comments,
        corrections=body.corrections,
    )
    return ReviewResponse.from_entity(review)


@router.get("/tenders/{tender_id}/reviews", response_model=list[ReviewResponse])
async def review_history(
    tender_id: UUID,
    service: ReviewService = Depends(get_review_service),
    _: User = Depends(get_current_user),
) -> list[ReviewResponse]:
    reviews = await service.history(tender_id)
    # Read once and share: staleness is the same comparison for every record.
    updated_at = await service.metadata_updated_at(tender_id)
    return [ReviewResponse.from_entity(r, metadata_updated_at=updated_at) for r in reviews]


@router.get("/reviews/pending", response_model=PageResponse[TenderResponse])
async def pending_queue(
    service: ReviewService = Depends(get_review_service),
    _: User = Depends(require_role(UserRole.EMPLOYEE)),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PageResponse[TenderResponse]:
    page = await service.pending(PageRequest(limit=limit, offset=offset))
    return PageResponse.of(page, [TenderResponse.from_entity(t) for t in page.items])
