"""Platform statistics, system health and API usage (FR-605, FR-607, FR-608)."""

from __future__ import annotations

from collections import Counter

import psutil
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.application.dto.admin import (
    ApiUsage,
    ComponentStatus,
    HostResources,
    PlatformStats,
    SystemHealth,
)
from tender_intel.application.dto.stats import OperationalStats
from tender_intel.domain.interfaces.providers import VectorStore
from tender_intel.infrastructure.observability.telemetry import collect_request_samples
from tender_intel.infrastructure.repositories.stats_repo import SqlAlchemyStatsRepository

_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024


class PlatformService:
    def __init__(
        self,
        *,
        stats: SqlAlchemyStatsRepository,
        session: AsyncSession,
        vectors: VectorStore,
    ) -> None:
        self._stats = stats
        self._session = session
        self._vectors = vectors

    async def platform_stats(self) -> PlatformStats:
        return await self._stats.platform_stats()

    async def operational_stats(self) -> OperationalStats:
        return await self._stats.operational_stats()

    async def system_health(self) -> SystemHealth:
        components = [await self._database_status(), await self._vector_status()]
        healthy = all(c.status == "ok" for c in components)
        return SystemHealth(healthy=healthy, components=components, host=self._host_resources())

    def api_usage(self) -> ApiUsage:
        by_status: Counter[str] = Counter()
        by_method: Counter[str] = Counter()
        total = 0.0
        for labels, value in collect_request_samples():
            total += value
            status = labels.get("status", "")
            if status[:1].isdigit():
                by_status[f"{status[0]}xx"] += int(value)
            by_method[labels.get("method", "UNKNOWN")] += int(value)
        return ApiUsage(
            total_requests=int(total),
            by_status_class=dict(by_status),
            by_method=dict(by_method),
        )

    # ------------------------------------------------------------------ #
    async def _database_status(self) -> ComponentStatus:
        try:
            await self._session.execute(text("SELECT 1"))
        except Exception as exc:
            return ComponentStatus("database", "error", str(exc))
        return ComponentStatus("database", "ok")

    async def _vector_status(self) -> ComponentStatus:
        ok = await self._vectors.health()
        return ComponentStatus("vector_store", "ok" if ok else "error")

    @staticmethod
    def _host_resources() -> HostResources:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return HostResources(
            cpu_percent=psutil.cpu_percent(interval=None),
            memory_percent=memory.percent,
            memory_total_mb=round(memory.total / _MB, 1),
            memory_used_mb=round(memory.used / _MB, 1),
            disk_percent=disk.percent,
            disk_total_gb=round(disk.total / _GB, 1),
            disk_used_gb=round(disk.used / _GB, 1),
        )
