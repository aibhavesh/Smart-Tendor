"""SQLAlchemy user and session repositories."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities import User, UserSession
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.infrastructure.db.orm import UserModel, UserSessionModel
from tender_intel.infrastructure.repositories import mappers


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> User:
        model = mappers.user_to_model(user)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.user_to_domain(model)

    async def get(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return mappers.user_to_domain(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(func.lower(UserModel.email) == email.lower())
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.user_to_domain(model) if model else None

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        stmt = select(UserModel).where(UserModel.google_sub == google_sub)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.user_to_domain(model) if model else None

    async def list(self, page: PageRequest) -> Page[User]:
        total = (await self._session.execute(select(func.count(UserModel.id)))).scalar_one()
        stmt = (
            select(UserModel)
            .order_by(UserModel.created_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return Page(
            items=[mappers.user_to_domain(m) for m in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def update(self, user: User) -> User:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            raise ValueError(f"user {user.id} not found for update")
        mappers.user_apply(model, user)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.user_to_domain(model)

    async def delete(self, user_id: UUID) -> None:
        model = await self._session.get(UserModel, user_id)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()


class SqlAlchemyUserSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: UserSession) -> UserSession:
        model = mappers.session_to_model(session)
        self._session.add(model)
        await self._session.flush()
        return mappers.session_to_domain(model)

    async def get(self, session_id: UUID) -> UserSession | None:
        model = await self._session.get(UserSessionModel, session_id)
        return mappers.session_to_domain(model) if model else None

    async def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        stmt = select(UserSessionModel).where(UserSessionModel.refresh_token_hash == token_hash)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.session_to_domain(model) if model else None

    async def list_for_user(self, user_id: UUID) -> list[UserSession]:
        stmt = (
            select(UserSessionModel)
            .where(UserSessionModel.user_id == user_id)
            .order_by(UserSessionModel.created_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.session_to_domain(m) for m in rows]

    async def update(self, session: UserSession) -> UserSession:
        model = await self._session.get(UserSessionModel, session.id)
        if model is None:
            raise ValueError(f"session {session.id} not found for update")
        model.revoked_at = session.revoked_at
        model.expires_at = session.expires_at
        await self._session.flush()
        return mappers.session_to_domain(model)
