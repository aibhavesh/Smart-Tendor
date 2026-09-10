"""Read-only platform statistics via aggregate queries (FR-605)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.application.dto.admin import PlatformStats
from tender_intel.application.dto.stats import OperationalStats
from tender_intel.domain.enums.review import ReviewKind
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.infrastructure.db.orm import (
    PastProjectModel,
    TenderDocumentModel,
    TenderModel,
    TenderReviewModel,
    UserModel,
)


class SqlAlchemyStatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def platform_stats(self) -> PlatformStats:
        tenders_by_status = await self._group_count(TenderModel.status)
        users_by_role = await self._group_count(UserModel.role)
        users_active = await self._count(UserModel, UserModel.is_active.is_(True))

        return PlatformStats(
            tenders_total=sum(tenders_by_status.values()),
            tenders_by_status=tenders_by_status,
            users_total=sum(users_by_role.values()),
            users_active=users_active,
            users_by_role=users_by_role,
            past_projects_total=await self._count(PastProjectModel),
            # Verdicts only. Corrections share this table but are not decisions,
            # and counting them here would report reviews nobody performed.
            reviews_total=await self._count(
                TenderReviewModel, TenderReviewModel.kind == ReviewKind.VERDICT.value
            ),
            documents_total=await self._count(TenderDocumentModel),
        )

    async def operational_stats(self) -> OperationalStats:
        """Aggregates any authenticated user may see (no user or account figures)."""
        tenders_by_status = await self._group_count(TenderModel.status)
        return OperationalStats(
            tenders_total=sum(tenders_by_status.values()),
            tenders_by_status=tenders_by_status,
            past_projects_total=await self._count(PastProjectModel),
            # Pending review == analysed but not yet reviewed; a review advances the
            # tender to REVIEWED, so the ANALYZED bucket *is* the queue depth.
            reviews_pending=tenders_by_status.get(TenderStatus.ANALYZED.value, 0),
        )

    async def _count(self, model: Any, *conditions: Any) -> int:
        stmt = select(func.count()).select_from(model)
        for cond in conditions:
            stmt = stmt.where(cond)
        return int((await self._session.execute(stmt)).scalar_one())

    async def _group_count(self, column: Any) -> dict[str, int]:
        stmt = select(column, func.count()).group_by(column)
        rows = (await self._session.execute(stmt)).all()
        return {str(key): int(count) for key, count in rows}
