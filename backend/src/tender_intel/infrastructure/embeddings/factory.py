"""Embedding-provider selection."""

from __future__ import annotations

from tender_intel.core.config import Settings
from tender_intel.domain.interfaces.providers import EmbeddingProvider
from tender_intel.infrastructure.embeddings.hash_embedding import HashEmbeddingProvider


def resolve_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_backend.lower() == "hash":
        return HashEmbeddingProvider(dimension=settings.embedding_dim)
    from tender_intel.infrastructure.embeddings.fastembed_provider import FastEmbedProvider

    return FastEmbedProvider(model_name=settings.embedding_model, dimension=settings.embedding_dim)
