"""Administration & monitoring response/request schemas."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr

from tender_intel.application.dto.admin import ApiUsage, PlatformStats, SystemHealth
from tender_intel.domain.entities import AuditLog, RoleAssignment
from tender_intel.domain.enums.roles import UserRole


class RoleUpdateRequest(BaseModel):
    role: UserRole


class ActiveUpdateRequest(BaseModel):
    is_active: bool


class RoleAssignmentCreateRequest(BaseModel):
    """Pre-provision an elevated role for someone who has not signed in yet.

    ``role`` is validated against the elevated set in the service layer, not
    here, so the rejection reads as a domain rule rather than a schema quirk.
    """

    email: EmailStr
    role: UserRole


class RoleAssignmentResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    assigned_by: UUID | None
    assigned_at: datetime
    consumed_at: datetime | None
    consumed_user_id: UUID | None
    is_consumed: bool

    @classmethod
    def from_entity(cls, a: RoleAssignment) -> RoleAssignmentResponse:
        return cls(
            id=a.id,
            email=a.email,
            role=a.role,
            assigned_by=a.assigned_by,
            assigned_at=a.assigned_at,
            consumed_at=a.consumed_at,
            consumed_user_id=a.consumed_user_id,
            is_consumed=a.is_consumed,
        )


class AuditLogResponse(BaseModel):
    id: UUID
    action: str
    entity_type: str
    entity_id: str | None
    actor_id: UUID | None
    diff: dict[str, Any]
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    @classmethod
    def from_entity(cls, a: AuditLog) -> AuditLogResponse:
        return cls(
            id=a.id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            actor_id=a.actor_id,
            diff=a.diff,
            ip_address=a.ip_address,
            user_agent=a.user_agent,
            created_at=a.created_at,
        )


class PlatformStatsResponse(BaseModel):
    tenders_total: int
    tenders_by_status: dict[str, int]
    users_total: int
    users_active: int
    users_by_role: dict[str, int]
    past_projects_total: int
    reviews_total: int
    documents_total: int

    @classmethod
    def from_dto(cls, s: PlatformStats) -> PlatformStatsResponse:
        return cls(**asdict(s))


class ComponentStatusResponse(BaseModel):
    name: str
    status: str
    detail: str | None


class HostResourcesResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_total_mb: float
    memory_used_mb: float
    disk_percent: float
    disk_total_gb: float
    disk_used_gb: float


class SystemHealthResponse(BaseModel):
    healthy: bool
    components: list[ComponentStatusResponse]
    host: HostResourcesResponse

    @classmethod
    def from_dto(cls, h: SystemHealth) -> SystemHealthResponse:
        return cls(
            healthy=h.healthy,
            components=[ComponentStatusResponse(**asdict(c)) for c in h.components],
            host=HostResourcesResponse(**asdict(h.host)),
        )


class ApiUsageResponse(BaseModel):
    total_requests: int
    by_status_class: dict[str, int]
    by_method: dict[str, int]

    @classmethod
    def from_dto(cls, u: ApiUsage) -> ApiUsageResponse:
        return cls(**asdict(u))
