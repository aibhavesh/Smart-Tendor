"""Operational statistics for any authenticated user.

``/admin/stats`` answers the same shape of question but requires ADMIN and includes user
and account figures. Without this endpoint a non-admin dashboard has to issue one
``GET /tenders?status=…&limit=1`` per status and read ``total`` off each envelope, which
is a request per lifecycle state to render a single counter row.

Nothing here is newly disclosed: every figure is an aggregate over records the caller can
already enumerate through the paginated list endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from tender_intel.api.dependencies.auth import get_current_user
from tender_intel.api.dependencies.services import get_platform_service
from tender_intel.api.schemas.stats import OperationalStatsResponse
from tender_intel.application.services.platform_service import PlatformService
from tender_intel.domain.entities import User

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=OperationalStatsResponse)
async def operational_stats(
    service: PlatformService = Depends(get_platform_service),
    _: User = Depends(get_current_user),
) -> OperationalStatsResponse:
    return OperationalStatsResponse.from_dto(await service.operational_stats())
