"""SQLAlchemy audit-log repository. Append-only (never updated or deleted)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities import AuditLog
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.infrastructure.db.orm import AuditLogModel
from tender_intel.infrastructure.repositories import mappers


class SqlAlchemyAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditLog) -> AuditLog:
        model = mappers.audit_to_model(entry)
        self._session.add(model)
        await self._session.flush()
        return mappers.audit_to_domain(model)

    async def list(
        self,
        page: PageRequest,
        *,
        actor_id: UUID | None = None,
        entity_type: str | None = None,
        action: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Page[AuditLog]:
        conditions = []
        if actor_id is not None:
            conditions.append(AuditLogModel.actor_id == actor_id)
        if entity_type is not None:
            conditions.append(AuditLogModel.entity_type == entity_type)
        if action is not None:
            conditions.append(AuditLogModel.action == action)
        if date_from is not None:
            conditions.append(
                AuditLogModel.created_at >= datetime.combine(date_from, time.min, UTC)
            )
        if date_to is not None:
            conditions.append(AuditLogModel.created_at <= datetime.combine(date_to, time.max, UTC))

        count_stmt = select(func.count(AuditLogModel.id))
        list_stmt = select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            list_stmt = list_stmt.where(cond)

        total = (await self._session.execute(count_stmt)).scalar_one()
        rows = (
            (await self._session.execute(list_stmt.limit(page.limit).offset(page.offset)))
            .scalars()
            .all()
        )
        return Page(
            items=[mappers.audit_to_domain(m) for m in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )
