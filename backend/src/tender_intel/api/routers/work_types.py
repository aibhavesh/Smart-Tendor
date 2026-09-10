"""Work-type taxonomy administration routes (feature spec §8).

Reading the taxonomy is level 20; every mutation is ADMIN. Types are deactivated
rather than deleted, so there is no DELETE for a work type — only for an alias,
which carries no history of its own.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from tender_intel.api.dependencies.auth import get_current_user, require_role
from tender_intel.api.dependencies.services import get_work_type_service
from tender_intel.api.schemas.common import PageResponse
from tender_intel.api.schemas.work_type import (
    AliasCreateRequest,
    AliasResponse,
    ProjectTagRequest,
    ProjectTagResponse,
    WorkTypeCreateRequest,
    WorkTypePatchRequest,
    WorkTypeResponse,
)
from tender_intel.application.services.work_type_service import WorkTypeService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.enums.work_type import WorkTypeCategory
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest

router = APIRouter(prefix="/api/v1", tags=["work-types"])


@router.get("/work-types", response_model=PageResponse[WorkTypeResponse])
async def list_work_types(
    service: WorkTypeService = Depends(get_work_type_service),
    _: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    category: WorkTypeCategory | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> PageResponse[WorkTypeResponse]:
    page = await service.list(
        PageRequest(limit=limit, offset=offset),
        category=category.value if category else None,
        is_active=is_active,
    )
    return PageResponse.of(page, [WorkTypeResponse.from_entity(w) for w in page.items])


@router.post("/work-types", status_code=status.HTTP_201_CREATED, response_model=WorkTypeResponse)
async def create_work_type(
    body: WorkTypeCreateRequest,
    service: WorkTypeService = Depends(get_work_type_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> WorkTypeResponse:
    created = await service.create(
        code=body.code.strip(),
        name=body.name.strip(),
        category=body.category,
        description=body.description,
        actor_id=actor.id,
    )
    return WorkTypeResponse.from_entity(created)


@router.get("/work-types/{work_type_id}", response_model=WorkTypeResponse)
async def get_work_type(
    work_type_id: UUID,
    service: WorkTypeService = Depends(get_work_type_service),
    _: User = Depends(get_current_user),
) -> WorkTypeResponse:
    return WorkTypeResponse.from_entity(await service.get_or_404(work_type_id))


@router.patch("/work-types/{work_type_id}", response_model=WorkTypeResponse)
async def patch_work_type(
    work_type_id: UUID,
    body: WorkTypePatchRequest,
    service: WorkTypeService = Depends(get_work_type_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> WorkTypeResponse:
    updated = await service.patch(
        work_type_id,
        name=body.name,
        category=body.category,
        description=body.description,
        actor_id=actor.id,
    )
    return WorkTypeResponse.from_entity(updated)


@router.post("/work-types/{work_type_id}/deactivate", response_model=WorkTypeResponse)
async def deactivate_work_type(
    work_type_id: UUID,
    service: WorkTypeService = Depends(get_work_type_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> WorkTypeResponse:
    """Retire a type from matching without losing why past tenders matched it."""
    return WorkTypeResponse.from_entity(await service.deactivate(work_type_id, actor_id=actor.id))


@router.post(
    "/work-types/{work_type_id}/aliases",
    status_code=status.HTTP_201_CREATED,
    response_model=AliasResponse,
)
async def add_alias(
    work_type_id: UUID,
    body: AliasCreateRequest,
    service: WorkTypeService = Depends(get_work_type_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> AliasResponse:
    created = await service.add_alias(
        work_type_id, alias=body.alias, kind=body.kind, actor_id=actor.id
    )
    return AliasResponse.from_entity(created)


@router.delete(
    "/work-types/{work_type_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_alias(
    work_type_id: UUID,
    alias_id: UUID,
    service: WorkTypeService = Depends(get_work_type_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    await service.remove_alias(work_type_id, alias_id, actor_id=actor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/work-types",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectTagResponse,
)
async def tag_project(
    project_id: UUID,
    body: ProjectTagRequest,
    service: WorkTypeService = Depends(get_work_type_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> ProjectTagResponse:
    tag = await service.tag_project(
        project_id,
        body.work_type_id,
        source=body.source,
        confidence=body.confidence,
        evidence=body.evidence,
        actor_id=actor.id,
    )
    return ProjectTagResponse.from_entity(tag)


@router.delete(
    "/projects/{project_id}/work-types/{work_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def untag_project(
    project_id: UUID,
    work_type_id: UUID,
    service: WorkTypeService = Depends(get_work_type_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    await service.untag_project(project_id, work_type_id, actor_id=actor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
