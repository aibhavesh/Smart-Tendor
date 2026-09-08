"""Dependency-injection wiring.

A single composition root (``Container``) constructs settings, the async engine
and the session factory. Repositories, providers and application services are
registered here as later phases add them, so the API layer never constructs its
own infrastructure — it resolves everything from the container.
"""

from __future__ import annotations

from dependency_injector import containers, providers

from tender_intel.core.config import Settings, get_settings
from tender_intel.infrastructure.db.session import create_engine, create_session_factory
from tender_intel.infrastructure.embeddings.factory import resolve_embedding_provider
from tender_intel.infrastructure.vector.qdrant_store import (
    QdrantVectorStore,
    create_qdrant_client,
)


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        packages=["tender_intel.api"],
    )

    settings: providers.Provider[Settings] = providers.Singleton(get_settings)

    engine = providers.Singleton(create_engine, settings=settings)
    session_factory = providers.Singleton(create_session_factory, engine=engine)

    # Embeddings + vector store are expensive to construct (model load, client
    # connection), so they are app-scoped singletons reused across requests.
    embedding_provider = providers.Singleton(resolve_embedding_provider, settings=settings)
    qdrant_client = providers.Singleton(create_qdrant_client, settings=settings)
    vector_store = providers.Singleton(QdrantVectorStore, client=qdrant_client)
