"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Force a hermetic test environment before Settings is constructed.
os.environ.setdefault("ENVIRONMENT", "ci")
os.environ.setdefault("JWT_SECRET", "test-secret-value-that-is-long-enough-1234")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://tender:tender@localhost:5432/test")


@pytest.fixture(scope="session")
def app():
    from tender_intel.api.app import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
