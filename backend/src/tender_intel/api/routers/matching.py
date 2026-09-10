"""Semantic matching route (FR-220..FR-235)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from tender_intel.api.dependencies.auth import get_current_user
from tender_intel.api.dependencies.services import get_matching_service
from tender_intel.api.schemas.matching import MatchResponse
from tender_intel.application.services.matching_service import MatchingService
from tender_intel.domain.entities import User

router = APIRouter(prefix="/tenders/{tender_id}", tags=["matching"])


@router.get("/matches", response_model=MatchResponse)
async def get_matches(
    tender_id: UUID,
    service: MatchingService = Depends(get_matching_service),
    _: User = Depends(get_current_user),
    top_k: int = Query(default=10, ge=1, le=50),
) -> MatchResponse:
    result = await service.match(tender_id, top_k=top_k)
    return MatchResponse.from_dto(result)
