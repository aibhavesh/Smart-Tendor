"""Qdrant vector store adapter (implements the VectorStore port).

Connection resolution (NFR: local-path fallback):
* ``QDRANT_URL`` set  -> remote server.
* otherwise           -> embedded local mode at ``QDRANT_LOCAL_PATH``.
Tests pass ``location=":memory:"`` explicitly.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qmodels

from tender_intel.core.config import Settings
from tender_intel.domain.interfaces.providers import VectorMatch, VectorRecord


def create_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    if settings.qdrant_url:
        return AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return AsyncQdrantClient(path=settings.qdrant_local_path)


class QdrantVectorStore:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def ensure_collection(self, name: str, dimension: int) -> None:
        if await self._client.collection_exists(name):
            return
        await self._client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE),
        )

    async def upsert(
        self, collection: str, id: UUID, vector: list[float], payload: dict[str, Any]
    ) -> None:
        await self._client.upsert(
            collection_name=collection,
            points=[qmodels.PointStruct(id=str(id), vector=vector, payload=payload)],
        )

    async def search(self, collection: str, vector: list[float], limit: int) -> list[VectorMatch]:
        results = await self._client.query_points(
            collection_name=collection, query=vector, limit=limit, with_payload=True
        )
        return [
            VectorMatch(id=UUID(str(point.id)), score=point.score, payload=point.payload or {})
            for point in results.points
        ]

    async def retrieve(self, collection: str, ids: list[UUID]) -> list[VectorRecord]:
        """Fetch stored vectors by id, skipping any point that has none."""
        if not ids:
            return []
        if not await self._client.collection_exists(collection):
            return []
        points = await self._client.retrieve(
            collection_name=collection,
            ids=[str(i) for i in ids],
            with_vectors=True,
            with_payload=False,
        )
        records: list[VectorRecord] = []
        for point in points:
            vector = point.vector
            # Qdrant types this as a single vector or a list of named ones;
            # only the flat form is stored here, so the nested case is skipped.
            if isinstance(vector, list) and (not vector or not isinstance(vector[0], list)):
                records.append(
                    VectorRecord(id=UUID(str(point.id)), vector=cast(list[float], vector))
                )
        return records

    async def delete(self, collection: str, id: UUID) -> None:
        await self._client.delete(
            collection_name=collection,
            points_selector=qmodels.PointIdsList(points=[str(id)]),
        )

    async def health(self) -> bool:
        try:
            await self._client.get_collections()
        except Exception:
            return False
        return True
