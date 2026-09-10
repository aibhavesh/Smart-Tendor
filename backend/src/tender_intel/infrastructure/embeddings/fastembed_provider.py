"""bge-small-en-v1.5 embeddings via fastembed (384-d).

The model is loaded lazily and warmed at startup. Note: the embedding model and
the Qdrant collection dimension must change together — both are driven by
``Settings.embedding_dim``.
"""

from __future__ import annotations

from typing import Any


class FastEmbedProvider:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", dimension: int = 384) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._model: Any = None

    @property
    def dimension(self) -> int:
        return self._dimension

    def _ensure_model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def warm(self) -> None:
        self._ensure_model()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        if not texts:
            return []
        model = self._ensure_model()
        vectors = await asyncio.to_thread(lambda: list(model.embed(texts)))
        return [vector.tolist() for vector in vectors]
