"""Phase 5 hash-embedding provider tests."""

from __future__ import annotations

import math

from tender_intel.infrastructure.embeddings.hash_embedding import HashEmbeddingProvider


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_dimension_and_normalisation():
    provider = HashEmbeddingProvider(dimension=384)
    assert provider.dimension == 384
    (vec,) = await provider.embed(["road construction work"])
    assert len(vec) == 384
    assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, rel_tol=1e-9)


async def test_deterministic():
    provider = HashEmbeddingProvider()
    a = (await provider.embed(["same text"]))[0]
    b = (await provider.embed(["same text"]))[0]
    assert a == b


async def test_shared_tokens_are_more_similar_than_unrelated():
    provider = HashEmbeddingProvider()
    query, related, unrelated = await provider.embed(
        ["road construction", "road widening construction", "aviation catering menu"]
    )
    assert _cosine(query, related) > _cosine(query, unrelated)


async def test_empty_text_is_zero_vector():
    provider = HashEmbeddingProvider(dimension=8)
    (vec,) = await provider.embed([""])
    assert vec == [0.0] * 8
