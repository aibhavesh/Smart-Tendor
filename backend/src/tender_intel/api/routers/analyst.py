"""AI Analyst report route (FR-330..FR-335)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from tender_intel.api.dependencies.auth import get_current_user
from tender_intel.api.dependencies.services import get_analyst_service, get_review_service
from tender_intel.api.schemas.analyst import AnalystReportResponse
from tender_intel.application.services.analyst_service import AnalystService
from tender_intel.application.services.review_service import ReviewService
from tender_intel.domain.entities import User

router = APIRouter(prefix="/tenders/{tender_id}", tags=["analyst"])


@router.get("/report", response_model=AnalystReportResponse)
async def get_report(
    tender_id: UUID,
    service: AnalystService = Depends(get_analyst_service),
    reviews: ReviewService = Depends(get_review_service),
    _: User = Depends(get_current_user),
) -> AnalystReportResponse:
    report = await service.generate_report(tender_id)
    # The prose is regenerated from current data; the recorded verdict may not be.
    return AnalystReportResponse.from_report(
        report, verdict_is_stale=await reviews.verdict_is_stale(tender_id)
    )
