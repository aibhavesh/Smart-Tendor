"""In-memory SQLite fixtures for repository and API integration tests.

``ORG_DOMAIN`` is the allowlisted domain the test app is configured with. Tests
that exercise the admission gate must use addresses on it; tests that seed
accounts directly through the repository bypass the gate and may use anything.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tender_intel.api.app import create_app
from tender_intel.api.dependencies.db import get_session
from tender_intel.api.dependencies.providers import get_embedding_provider, get_vector_store
from tender_intel.core.config import Environment, Settings
from tender_intel.infrastructure.db.models import Base
from tender_intel.infrastructure.embeddings.hash_embedding import HashEmbeddingProvider
from tender_intel.infrastructure.vector.qdrant_store import QdrantVectorStore

ORG_DOMAIN = "maheshwaricomputers.com"


def _make_engine():
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def app_db() -> AsyncIterator[FastAPI]:
    """A create_app() instance whose DB session is a fresh in-memory SQLite."""
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    settings = Settings(
        environment=Environment.CI,
        debug=True,
        jwt_secret="test-secret-value-that-is-long-enough-1234",
        enable_document_worker=False,
        allowed_email_domains=[ORG_DOMAIN],
    )
    app = create_app(settings)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    # Offline embeddings + in-memory Qdrant so tests never load a model or hit disk.
    qdrant = AsyncQdrantClient(location=":memory:")
    vector_store = QdrantVectorStore(qdrant)
    embeddings = HashEmbeddingProvider(dimension=settings.embedding_dim)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_embedding_provider] = lambda: embeddings
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    # Expose the factory and settings so tests can seed accounts and mint
    # tokens directly, bypassing both the admission gate and password
    # hashing — most tests just need an authenticated caller and don't care
    # which sign-in method it used.
    app.state.test_session_factory = factory
    app.state.test_settings = settings
    yield app
    await qdrant.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(app_db: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app_db)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
