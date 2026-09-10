"""Request-scoped database session and container access."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.core.config import Settings
from tender_intel.core.container import Container


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_app_settings(request: Request) -> Settings:
    return get_container(request).settings()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session, committing on success (overridable in tests)."""
    factory = get_container(request).session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
