"""Application configuration.

All configuration is sourced from the environment (Cross-cutting requirement:
"No hardcoded secrets"). Three values act as production *release gates* and are
validated on startup by :func:`enforce_release_gates`:

* ``JWT_SECRET`` must not be the insecure default.
* ``CORS_ALLOW_ORIGINS`` must be an explicit allowlist (no ``*``) in production.
* ``DATABASE_URL`` must be explicitly set to PostgreSQL in production.
* ``ALLOWED_EMAIL_DOMAINS`` must name at least one organisation domain.
* ``METRICS_PASSWORD`` must be changed or metrics must be disabled.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_JWT_SECRET = "change-me-in-production"
INSECURE_METRICS_PASSWORD = "metrics"
DEFAULT_CORS_ALLOW_ORIGINS = ("http://localhost:3000",)


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = Environment.LOCAL
    debug: bool = False

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # NoDecode: keep the raw env string (no JSON decode) so the "before" validator
    # below can split a plain comma-separated allowlist.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        # Local convenience only. Production requires an explicitly supplied
        # allowlist in enforce_release_gates().
        default_factory=lambda: list(DEFAULT_CORS_ALLOW_ORIGINS)
    )

    # --- Database ---
    # Postgres in every deployed environment. The annotation admits a plain DSN
    # string so local development on a machine without a Postgres server can
    # point this at SQLite — the schema and the migration chain are already
    # SQLite-compatible by design (see infrastructure/db/base.py, and the
    # batch_alter_table calls in alembic/versions). Production is held to
    # Postgres by enforce_release_gates, not by this annotation.
    database_url: PostgresDsn | str = Field(
        default="postgresql+asyncpg://tender:tender@localhost:5432/tender_intel"
    )
    db_echo: bool = False

    # --- Auth ---
    jwt_secret: str = INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # --- Account admission ---
    # Organisation domains permitted to hold an account. The organisation may
    # run more than one, so this is a list. Fail-closed: an empty list rejects
    # every sign-in, and production additionally refuses to start (see
    # enforce_release_gates). NoDecode for the same reason as CORS above.
    allowed_email_domains: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Individually admitted addresses, for the occasional person who must have
    # access but is not on an organisation domain — an external consultant, a
    # contractor, a developer. Deliberately per *address*, not per domain:
    # widening the domain list to admit one person opens the door to everyone
    # who shares their email provider.
    #
    # Keep this list short and review it. Every entry is a standing exception to
    # the rule that only the organisation can hold an account.
    allowed_email_exceptions: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Email seeded as the first SUPER_ADMIN role assignment. Never commit a
    # real address; the bootstrap migration no-ops when this is unset.
    bootstrap_super_admin_email: str | None = None

    # --- Vector store / embeddings ---
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_local_path: str = "./.qdrant"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_backend: str = "fastembed"  # or "hash" (deterministic, offline/dev)
    qdrant_collection: str = "past_projects"
    warm_embeddings_on_startup: bool = True

    # --- AI Analyst ---
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    # --- Document pipeline ---
    storage_dir: str = "./.storage"
    download_poll_seconds: int = 15
    enable_document_worker: bool = True

    # --- Extraction ---
    extraction_text_backend: str = "pdfplumber"  # or "pymupdf"

    # --- Decision engines: company financials (post-v1: admin-managed config) ---
    company_turnover: Decimal | None = None
    company_net_worth: Decimal | None = None

    # --- Observability ---
    metrics_enabled: bool = True
    metrics_user: str = "metrics"
    metrics_password: str = INSECURE_METRICS_PASSWORD
    enable_frontend_logs: bool = True
    # Frontend log ingestion accepts anonymous callers on purpose — the errors
    # worth capturing happen on the sign-in and landing screens, before anyone
    # has a token. The rate limit is what keeps that from being an open write
    # amplifier. Counted in log *entries* per minute, per user (or per client
    # address when anonymous), and enforced per worker process. 0 disables it.
    #
    # The browser client flushes at most 50 entries every 10s, so 300/min is its
    # steady ceiling; the default leaves room for bursts without leaving the
    # door open.
    frontend_log_entries_per_minute: int = 600
    otel_exporter_otlp_endpoint: str | None = None
    sentry_dsn: str | None = None
    log_level: str = "INFO"
    json_logs: bool = True

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _select_async_postgres_driver(cls, v: object) -> object:
        """Accept provider Postgres URLs while consistently selecting asyncpg."""
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return "postgresql+asyncpg://" + v.removeprefix("postgres://")
            if v.startswith("postgresql://"):
                return "postgresql+asyncpg://" + v.removeprefix("postgresql://")
        return v

    @field_validator("allowed_email_domains", "allowed_email_exceptions", mode="before")
    @classmethod
    def _split_domains(cls, v: object) -> object:
        """Split a comma-separated allowlist and normalise each entry.

        Shared by the domain list and the per-address exception list: both are
        lowercased and stripped here so the comparisons in ``assert_org_email``
        are plain set membership against values already in the same shape as the
        normalised address. A leading ``@`` is tolerated on a domain entry.
        """
        if isinstance(v, str):
            return [d.strip().lower().lstrip("@") for d in v.split(",") if d.strip()]
        if isinstance(v, list):
            return [str(d).strip().lower().lstrip("@") for d in v if str(d).strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


def enforce_release_gates(settings: Settings) -> None:
    """Fail fast in production on insecure configuration (Phase 13 hardening)."""
    if not settings.is_production:
        return
    errors: list[str] = []
    if settings.jwt_secret == INSECURE_JWT_SECRET or len(settings.jwt_secret) < 32:
        errors.append("JWT_SECRET must be set to a strong value (>=32 chars) in production.")
    if (
        "cors_allow_origins" not in settings.model_fields_set
        or not settings.cors_allow_origins
        or "*" in settings.cors_allow_origins
    ):
        errors.append(
            "CORS_ALLOW_ORIGINS must be explicitly set to an allowlist (no '*') in production."
        )
    if "database_url" not in settings.model_fields_set or not str(settings.database_url).startswith(
        "postgresql"
    ):
        errors.append(
            "DATABASE_URL must be explicitly set to a PostgreSQL DSN in production. "
            "SQLite is supported for local development only."
        )
    if not settings.allowed_email_domains:
        errors.append(
            "ALLOWED_EMAIL_DOMAINS must list at least one organisation domain in production; "
            "an empty allowlist rejects every sign-in."
        )
    if settings.metrics_enabled and (
        settings.metrics_password == INSECURE_METRICS_PASSWORD
        or len(settings.metrics_password) < 16
    ):
        errors.append(
            "METRICS_PASSWORD must be set to a strong value (>=16 chars) when metrics "
            "are enabled in production, or set METRICS_ENABLED=false."
        )
    if errors:
        raise RuntimeError("Release gate failure:\n- " + "\n- ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
