"""SQLAlchemy past-project repository."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities import PastProject
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.infrastructure.db.orm import PastProjectModel
from tender_intel.infrastructure.repositories import mappers


class SqlAlchemyPastProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, project: PastProject) -> PastProject:
        model = mappers.past_project_to_model(project)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.past_project_to_domain(model)

    async def get(self, project_id: UUID) -> PastProject | None:
        model = await self._session.get(PastProjectModel, project_id)
        return mappers.past_project_to_domain(model) if model else None

    async def get_many(self, ids: Sequence[UUID]) -> Sequence[PastProject]:
        if not ids:
            return []
        stmt = select(PastProjectModel).where(PastProjectModel.id.in_(list(ids)))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.past_project_to_domain(m) for m in rows]

    async def list(self, page: PageRequest) -> Page[PastProject]:
        total = (await self._session.execute(select(func.count(PastProjectModel.id)))).scalar_one()
        stmt = (
            select(PastProjectModel)
            .order_by(PastProjectModel.created_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return Page(
            items=[mappers.past_project_to_domain(m) for m in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def list_by_min_work_value(self, minimum: Decimal) -> Sequence[PastProject]:
        stmt = (
            select(PastProjectModel)
            .where(PastProjectModel.work_value >= minimum)
            .order_by(PastProjectModel.work_value.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.past_project_to_domain(m) for m in rows]

    async def list_unindexed(self, limit: int) -> Sequence[PastProject]:
        stmt = (
            select(PastProjectModel)
            .where(PastProjectModel.embedding_indexed.is_(False))
            .order_by(PastProjectModel.created_at.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.past_project_to_domain(m) for m in rows]

    async def update(self, project: PastProject) -> PastProject:
        model = await self._session.get(PastProjectModel, project.id)
        if model is None:
            raise ValueError(f"past project {project.id} not found for update")
        mappers.past_project_apply(model, project)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.past_project_to_domain(model)

    async def delete(self, project_id: UUID) -> None:
        model = await self._session.get(PastProjectModel, project_id)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()
