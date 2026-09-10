"""Administration & audit routes (FR-601..FR-608)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from tender_intel.api.dependencies.auth import require_role
from tender_intel.api.dependencies.services import get_admin_service, get_platform_service
from tender_intel.api.schemas.admin import (
    ActiveUpdateRequest,
    ApiUsageResponse,
    AuditLogResponse,
    PlatformStatsResponse,
    RoleAssignmentCreateRequest,
    RoleAssignmentResponse,
    RoleUpdateRequest,
    SystemHealthResponse,
)
from tender_intel.api.schemas.auth import UserResponse
from tender_intel.api.schemas.common import PageResponse
from tender_intel.application.services.admin_service import AdminService
from tender_intel.application.services.platform_service import PlatformService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest

router = APIRouter(prefix="/admin", tags=["admin"])


# --- User administration (ADMIN) ---
@router.get("/users", response_model=PageResponse[UserResponse])
async def list_users(
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PageResponse[UserResponse]:
    page = await service.list_users(PageRequest(limit=limit, offset=offset))
    return PageResponse.of(page, [UserResponse.from_entity(u) for u in page.items])


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> UserResponse:
    return UserResponse.from_entity(await service.get_user(user_id))


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def change_role(
    user_id: UUID,
    body: RoleUpdateRequest,
    service: AdminService = Depends(get_admin_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> UserResponse:
    return UserResponse.from_entity(await service.change_role(user_id, body.role, actor=actor))


@router.patch("/users/{user_id}/active", response_model=UserResponse)
async def set_active(
    user_id: UUID,
    body: ActiveUpdateRequest,
    service: AdminService = Depends(get_admin_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> UserResponse:
    return UserResponse.from_entity(await service.set_active(user_id, body.is_active, actor=actor))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    service: AdminService = Depends(get_admin_service),
    actor: User = Depends(require_role(UserRole.SUPER_ADMIN)),
) -> Response:
    await service.delete_user(user_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Pre-provisioned elevation list (ADMIN) ---
#
# These rows decide the role an account is *born* with. They are never read
# when authorising a request, and creating one for an address that already has
# an account is rejected rather than silently ignored.
@router.get("/role-assignments", response_model=PageResponse[RoleAssignmentResponse])
async def list_role_assignments(
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PageResponse[RoleAssignmentResponse]:
    page = await service.list_role_assignments(PageRequest(limit=limit, offset=offset))
    return PageResponse.of(page, [RoleAssignmentResponse.from_entity(a) for a in page.items])


@router.post(
    "/role-assignments",
    status_code=status.HTTP_201_CREATED,
    response_model=RoleAssignmentResponse,
)
async def create_role_assignment(
    body: RoleAssignmentCreateRequest,
    service: AdminService = Depends(get_admin_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> RoleAssignmentResponse:
    assignment = await service.create_role_assignment(email=body.email, role=body.role, actor=actor)
    return RoleAssignmentResponse.from_entity(assignment)


@router.delete("/role-assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_role_assignment(
    assignment_id: UUID,
    service: AdminService = Depends(get_admin_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> Response:
    await service.revoke_role_assignment(assignment_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Audit log (immutable; query only) ---
@router.get("/audit-logs", response_model=PageResponse[AuditLogResponse])
async def list_audit_logs(
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    actor_id: UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> PageResponse[AuditLogResponse]:
    page = await service.list_audit_logs(
        PageRequest(limit=limit, offset=offset),
        actor_id=actor_id,
        entity_type=entity_type,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return PageResponse.of(page, [AuditLogResponse.from_entity(a) for a in page.items])


# --- Monitoring ---
@router.get("/stats", response_model=PlatformStatsResponse)
async def platform_stats(
    service: PlatformService = Depends(get_platform_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> PlatformStatsResponse:
    return PlatformStatsResponse.from_dto(await service.platform_stats())


@router.get("/system-health", response_model=SystemHealthResponse)
async def system_health(
    service: PlatformService = Depends(get_platform_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> SystemHealthResponse:
    return SystemHealthResponse.from_dto(await service.system_health())


@router.get("/api-usage", response_model=ApiUsageResponse)
async def api_usage(
    service: PlatformService = Depends(get_platform_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> ApiUsageResponse:
    return ApiUsageResponse.from_dto(service.api_usage())
