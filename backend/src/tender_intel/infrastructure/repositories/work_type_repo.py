"""SQLAlchemy work-type taxonomy repository.

Covers the three tables the taxonomy spans — types, their aliases, and the tags
linking them to past projects — because they are read and written together and
splitting them would spread one aggregate across three call sites.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities.work_type import (
    PastProjectWorkType,
    WorkType,
    WorkTypeAlias,
)
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.infrastructure.db.orm import (
    PastProjectWorkTypeModel,
    WorkTypeAliasModel,
    WorkTypeModel,
)
from tender_intel.infrastructure.repositories import mappers


class SqlAlchemyWorkTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Work types
    # ------------------------------------------------------------------ #
    async def add(self, work_type: WorkType) -> WorkType:
        model = mappers.work_type_to_model(work_type)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.work_type_to_domain(model)

    async def get(self, work_type_id: UUID) -> WorkType | None:
        model = await self._session.get(WorkTypeModel, work_type_id)
        return mappers.work_type_to_domain(model) if model else None

    async def get_by_code(self, code: str) -> WorkType | None:
        stmt = select(WorkTypeModel).where(WorkTypeModel.code == code)
        model = (await self._session.execute(stmt)).scalars().first()
        return mappers.work_type_to_domain(model) if model else None

    async def list_active(self) -> list[WorkType]:
        """Every active type. The taxonomy is small enough to scan whole."""
        stmt = (
            select(WorkTypeModel)
            .where(WorkTypeModel.is_active.is_(True))
            .order_by(WorkTypeModel.code.asc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.work_type_to_domain(m) for m in rows]

    async def update(self, work_type: WorkType) -> WorkType:
        model = await self._session.get(WorkTypeModel, work_type.id)
        if model is None:
            raise ValueError(f"work type {work_type.id} not found for update")
        mappers.work_type_apply(model, work_type)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.work_type_to_domain(model)

    # ------------------------------------------------------------------ #
    # Aliases
    # ------------------------------------------------------------------ #
    async def add_alias(self, alias: WorkTypeAlias) -> WorkTypeAlias:
        model = mappers.alias_to_model(alias)
        self._session.add(model)
        await self._session.flush()
        return mappers.alias_to_domain(model)

    async def get_alias(self, alias_id: UUID) -> WorkTypeAlias | None:
        model = await self._session.get(WorkTypeAliasModel, alias_id)
        return mappers.alias_to_domain(model) if model else None

    async def find_alias(self, normalised: str) -> WorkTypeAlias | None:
        stmt = select(WorkTypeAliasModel).where(WorkTypeAliasModel.alias_normalised == normalised)
        model = (await self._session.execute(stmt)).scalars().first()
        return mappers.alias_to_domain(model) if model else None

    async def list_aliases(self, work_type_ids: Sequence[UUID]) -> list[WorkTypeAlias]:
        if not work_type_ids:
            return []
        stmt = select(WorkTypeAliasModel).where(
            WorkTypeAliasModel.work_type_id.in_(list(work_type_ids))
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.alias_to_domain(m) for m in rows]

    async def delete_alias(self, alias_id: UUID) -> None:
        model = await self._session.get(WorkTypeAliasModel, alias_id)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    # ------------------------------------------------------------------ #
    # Project tags
    # ------------------------------------------------------------------ #
    async def add_tag(self, tag: PastProjectWorkType) -> PastProjectWorkType:
        model = mappers.tag_to_model(tag)
        await self._session.merge(model)
        await self._session.flush()
        return tag

    async def delete_tag(self, project_id: UUID, work_type_id: UUID) -> None:
        await self._session.execute(
            delete(PastProjectWorkTypeModel).where(
                PastProjectWorkTypeModel.project_id == project_id,
                PastProjectWorkTypeModel.work_type_id == work_type_id,
            )
        )
        await self._session.flush()

    async def list_tags(self) -> list[PastProjectWorkType]:
        rows = (await self._session.execute(select(PastProjectWorkTypeModel))).scalars().all()
        return [mappers.tag_to_domain(m) for m in rows]

    # Declared last: naming a method ``list`` shadows the builtin for every
    # annotation that follows it in the class body.
    async def list(
        self, page: PageRequest, *, category: str | None = None, is_active: bool | None = None
    ) -> Page[WorkType]:
        conditions = []
        if category is not None:
            conditions.append(WorkTypeModel.category == category)
        if is_active is not None:
            conditions.append(WorkTypeModel.is_active.is_(is_active))

        count_stmt = select(func.count(WorkTypeModel.id))
        list_stmt = select(WorkTypeModel).order_by(WorkTypeModel.code.asc())
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
            list_stmt = list_stmt.where(condition)

        total = (await self._session.execute(count_stmt)).scalar_one()
        rows = (
            (await self._session.execute(list_stmt.limit(page.limit).offset(page.offset)))
            .scalars()
            .all()
        )
        return Page(
            items=[mappers.work_type_to_domain(m) for m in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
