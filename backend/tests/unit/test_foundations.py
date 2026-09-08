"""Phase 0 smoke tests: the app boots, health responds, and the release gates fire."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tender_intel.core.config import (
    DEFAULT_CORS_ALLOW_ORIGINS,
    INSECURE_JWT_SECRET,
    INSECURE_METRICS_PASSWORD,
    Environment,
    Settings,
    enforce_release_gates,
)


async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_cors_origins_parsed_from_csv():
    s = Settings(cors_allow_origins="http://a.com, http://b.com")  # type: ignore[arg-type]
    assert s.cors_allow_origins == ["http://a.com", "http://b.com"]


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_provider_database_urls_select_asyncpg(scheme):
    s = Settings(database_url=f"{scheme}user:pass@db.example.com/app")
    assert str(s.database_url) == "postgresql+asyncpg://user:pass@db.example.com/app"


def test_default_cors_is_local_only(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    s = Settings(_env_file=None)
    assert s.cors_allow_origins == list(DEFAULT_CORS_ALLOW_ORIGINS)
    assert s.cors_allow_origins == ["http://localhost:3000"]


async def test_cors_preflight_allows_an_explicit_frontend():
    from tender_intel.api.app import create_app

    origin = "https://app.example.com"
    app = create_app(
        Settings(
            environment=Environment.CI,
            cors_allow_origins=[origin],
            enable_document_worker=False,
            warm_embeddings_on_startup=False,
        )
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_release_gate_rejects_default_jwt_secret_in_production():
    s = Settings(environment=Environment.PRODUCTION, jwt_secret=INSECURE_JWT_SECRET)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        enforce_release_gates(s)


def test_release_gate_rejects_wildcard_cors_in_production():
    s = Settings(
        environment=Environment.PRODUCTION,
        jwt_secret="a-sufficiently-long-production-secret-value",
        cors_allow_origins=["*"],
    )
    with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
        enforce_release_gates(s)


def test_release_gate_rejects_implicit_cors_in_production():
    s = Settings(
        _env_file=None,
        environment=Environment.PRODUCTION,
        jwt_secret="a-sufficiently-long-production-secret-value",
        database_url="postgresql+asyncpg://user:pass@db.example.com/app",
        allowed_email_domains=["example.com"],
        metrics_enabled=False,
    )
    with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
        enforce_release_gates(s)


def test_release_gate_rejects_implicit_database_url_in_production(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(
        _env_file=None,
        environment=Environment.PRODUCTION,
        jwt_secret="a-sufficiently-long-production-secret-value",
        cors_allow_origins=["https://app.example.com"],
        allowed_email_domains=["example.com"],
        metrics_enabled=False,
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        enforce_release_gates(s)


def test_release_gate_rejects_default_metrics_password_in_production():
    s = Settings(
        environment=Environment.PRODUCTION,
        jwt_secret="a-sufficiently-long-production-secret-value",
        cors_allow_origins=["https://app.example.com"],
        database_url="postgresql+asyncpg://user:pass@db.example.com/app",
        allowed_email_domains=["example.com"],
        metrics_password=INSECURE_METRICS_PASSWORD,
    )
    with pytest.raises(RuntimeError, match="METRICS_PASSWORD"):
        enforce_release_gates(s)


def test_release_gate_accepts_complete_production_settings():
    enforce_release_gates(
        Settings(
            environment=Environment.PRODUCTION,
            jwt_secret="a-sufficiently-long-production-secret-value",
            cors_allow_origins=["https://app.example.com"],
            database_url="postgresql+asyncpg://user:pass@db.example.com/app",
            allowed_email_domains=["example.com"],
            metrics_password="a-separate-metrics-secret",
        )
    )


def test_release_gate_passes_local():
    enforce_release_gates(Settings(environment=Environment.LOCAL))
