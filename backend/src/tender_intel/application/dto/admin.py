"""Administration & monitoring DTOs (FR-601..FR-608)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PlatformStats:
    tenders_total: int
    tenders_by_status: dict[str, int]
    users_total: int
    users_active: int
    users_by_role: dict[str, int]
    past_projects_total: int
    reviews_total: int
    documents_total: int


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    name: str
    status: str  # "ok" | "error"
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class HostResources:
    cpu_percent: float
    memory_percent: float
    memory_total_mb: float
    memory_used_mb: float
    disk_percent: float
    disk_total_gb: float
    disk_used_gb: float


@dataclass(frozen=True, slots=True)
class SystemHealth:
    healthy: bool
    components: list[ComponentStatus]
    host: HostResources


@dataclass(frozen=True, slots=True)
class ApiUsage:
    total_requests: int
    by_status_class: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
