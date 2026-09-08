"""Phase 10 observability tests: metrics endpoint and frontend log ingestion."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from tender_intel.api.app import create_app
from tender_intel.core.config import Environment, Settings


@asynccontextmanager
async def _bare_client(**overrides) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        environment=Environment.CI,
        jwt_secret="test-secret-value-that-is-long-enough-1234",
        enable_document_worker=False,
        warm_embeddings_on_startup=False,
        **overrides,
    )
    transport = ASGITransport(app=create_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --- Metrics endpoint (FR-701) ---
async def test_metrics_requires_credentials(client):
    await client.get("/health")  # generate at least one request sample
    resp = await client.get("/metrics")
    assert resp.status_code == 401


async def test_metrics_rejects_wrong_credentials(client):
    resp = await client.get("/metrics", auth=("metrics", "wrong"))
    assert resp.status_code == 401


async def test_metrics_returns_exposition_with_credentials(client):
    await client.get("/health")
    resp = await client.get("/metrics", auth=("metrics", "metrics"))
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "http_requests_total" in resp.text


async def test_metrics_disabled_returns_404():
    async with _bare_client(metrics_enabled=False) as client:
        resp = await client.get("/metrics", auth=("metrics", "metrics"))
        assert resp.status_code == 404


# --- Frontend log ingestion (FR-706) ---
async def test_frontend_logs_accepted(client):
    resp = await client.post(
        "/observability/logs",
        json={
            "logs": [
                {"level": "error", "message": "Boom", "context": {"page": "/tenders"}},
                {"level": "info", "message": "Loaded"},
            ]
        },
    )
    assert resp.status_code == 202
    assert resp.json()["received"] == 2


async def test_frontend_logs_validation():
    async with _bare_client() as client:
        # Empty batch rejected.
        assert (await client.post("/observability/logs", json={"logs": []})).status_code == 422
        # Too many entries rejected.
        big = {"logs": [{"message": "x"} for _ in range(101)]}
        assert (await client.post("/observability/logs", json=big)).status_code == 422
        # Invalid level rejected.
        bad = {"logs": [{"level": "trace", "message": "x"}]}
        assert (await client.post("/observability/logs", json=bad)).status_code == 422


async def test_frontend_logs_disabled_returns_404():
    async with _bare_client(enable_frontend_logs=False) as client:
        resp = await client.post("/observability/logs", json={"logs": [{"message": "hi"}]})
        assert resp.status_code == 404


# --- Log ingestion is open on purpose, but not unbounded --- #
async def test_anonymous_ingestion_is_still_accepted():
    """The errors worth capturing happen before anyone holds a token."""
    async with _bare_client() as client:
        resp = await client.post(
            "/observability/logs", json={"logs": [{"message": "sign-in failed"}]}
        )
        assert resp.status_code == 202


async def test_a_garbage_token_does_not_reject_the_batch():
    """Attribution is best-effort. A bad token must not lose the diagnostics."""
    async with _bare_client() as client:
        resp = await client.post(
            "/observability/logs",
            json={"logs": [{"message": "hi"}]},
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 202


async def test_rate_limit_refuses_a_flood_and_says_when_to_retry():
    async with _bare_client(frontend_log_entries_per_minute=10) as client:
        body = {"logs": [{"message": "x"} for _ in range(10)]}
        assert (await client.post("/observability/logs", json=body)).status_code == 202

        refused = await client.post("/observability/logs", json=body)
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) > 0


async def test_rate_limit_counts_entries_not_requests():
    """A batch may carry a hundred entries; the entries are what reach the logs."""
    async with _bare_client(frontend_log_entries_per_minute=5) as client:
        # Six entries in one request already exceeds a five-entry budget.
        body = {"logs": [{"message": "x"} for _ in range(6)]}
        assert (await client.post("/observability/logs", json=body)).status_code == 429


async def test_rate_limit_of_zero_disables_it():
    async with _bare_client(frontend_log_entries_per_minute=0) as client:
        body = {"logs": [{"message": "x"} for _ in range(100)]}
        for _ in range(3):
            assert (await client.post("/observability/logs", json=body)).status_code == 202


async def test_oversized_context_is_truncated_not_rejected():
    """A whole batch must not be lost over one oversized entry."""
    async with _bare_client() as client:
        resp = await client.post(
            "/observability/logs",
            json={
                "logs": [
                    {
                        "message": "Boom",
                        "context": {
                            "stack": "x" * 50_000,
                            **{f"k{i}": i for i in range(50)},
                        },
                    }
                ]
            },
        )
        assert resp.status_code == 202
        assert resp.json()["received"] == 1


# --- Health (FR-707) ---
async def test_health_is_unauthenticated(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
