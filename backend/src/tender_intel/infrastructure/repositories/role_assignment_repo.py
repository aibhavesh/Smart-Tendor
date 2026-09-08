"""SQLAlchemy repository for the pre-provisioned elevation list."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities import RoleAssignment
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.infrastructure.db.orm import RoleAssignmentModel
from tender_intel.infrastructure.repositories import mappers


class SqlAlchemyRoleAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, assignment: RoleAssignment) -> RoleAssignment:
        model = mappers.role_assignment_to_model(assignment)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.role_assignment_to_domain(model)

    async def get(self, assignment_id: UUID) -> RoleAssignment | None:
        model = await self._session.get(RoleAssignmentModel, assignment_id)
        return mappers.role_assignment_to_domain(model) if model else None

    async def get_by_email(self, email: str) -> RoleAssignment | None:
        """Look up by email, case-insensitively.

        Rows are written normalised, so ``lower()`` here is belt-and-braces
        against a row seeded by hand or by an older migration.
        """
        stmt = select(RoleAssignmentModel).where(
            func.lower(RoleAssignmentModel.email) == email.strip().lower()
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.role_assignment_to_domain(model) if model else None

    async def list(self, page: PageRequest) -> Page[RoleAssignment]:
        total = (
            await self._session.execute(select(func.count(RoleAssignmentModel.id)))
        ).scalar_one()
        stmt = (
            select(RoleAssignmentModel)
            .order_by(RoleAssignmentModel.assigned_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return Page(
            items=[mappers.role_assignment_to_domain(m) for m in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def update(self, assignment: RoleAssignment) -> RoleAssignment:
        model = await self._session.get(RoleAssignmentModel, assignment.id)
        if model is None:
            raise ValueError(f"role assignment {assignment.id} not found for update")
        mappers.role_assignment_apply(model, assignment)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.role_assignment_to_domain(model)

    async def delete(self, assignment_id: UUID) -> None:
        model = await self._session.get(RoleAssignmentModel, assignment_id)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()
