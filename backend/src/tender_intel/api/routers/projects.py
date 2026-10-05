"""Past-project registry routes (FR-220..FR-235)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from tender_intel.api.dependencies.auth import get_current_user, require_role
from tender_intel.api.dependencies.services import get_past_project_service
from tender_intel.api.schemas.common import PageResponse
from tender_intel.api.schemas.past_project import (
    BackfillResponse,
    PastProjectBulkDeleteResponse,
    PastProjectCreateRequest,
    PastProjectPatchRequest,
    PastProjectResponse,
)
from tender_intel.application.services.past_project_service import PastProjectService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest

router = APIRouter(prefix="/projects", tags=["past-projects"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PastProjectResponse)
async def create_project(
    body: PastProjectCreateRequest,
    service: PastProjectService = Depends(get_past_project_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> PastProjectResponse:
    project = await service.create(body.to_dto(), actor_id=user.id)
    return PastProjectResponse.from_entity(project)


@router.get("", response_model=PageResponse[PastProjectResponse])
async def list_projects(
    service: PastProjectService = Depends(get_past_project_service),
    _: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PageResponse[PastProjectResponse]:
    page = await service.list(PageRequest(limit=limit, offset=offset))
    return PageResponse.of(page, [PastProjectResponse.from_entity(p) for p in page.items])


@router.delete("", response_model=PastProjectBulkDeleteResponse)
async def delete_all_projects(
    service: PastProjectService = Depends(get_past_project_service),
    user: User = Depends(require_role(UserRole.MANAGER)),
) -> PastProjectBulkDeleteResponse:
    """Permanently remove the entire past-project registry."""
    return PastProjectBulkDeleteResponse(deleted=await service.delete_all(actor_id=user.id))


@router.get("/{project_id}", response_model=PastProjectResponse)
async def get_project(
    project_id: UUID,
    service: PastProjectService = Depends(get_past_project_service),
    _: User = Depends(get_current_user),
) -> PastProjectResponse:
    return PastProjectResponse.from_entity(await service.get_or_404(project_id))


@router.patch("/{project_id}", response_model=PastProjectResponse)
async def patch_project(
    project_id: UUID,
    body: PastProjectPatchRequest,
    service: PastProjectService = Depends(get_past_project_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> PastProjectResponse:
    project = await service.patch(project_id, body.to_dto(), actor_id=user.id)
    return PastProjectResponse.from_entity(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    service: PastProjectService = Depends(get_past_project_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> Response:
    await service.delete(project_id, actor_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/backfill", response_model=BackfillResponse)
async def backfill(
    service: PastProjectService = Depends(get_past_project_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> BackfillResponse:
    return BackfillResponse(indexed=await service.backfill())
