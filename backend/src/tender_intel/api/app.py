"""FastAPI application factory and composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tender_intel import __version__
from tender_intel.api.errors import register_exception_handlers
from tender_intel.api.middleware import ObservabilityMiddleware
from tender_intel.api.routers import (
    admin,
    auth,
    company_turnover,
    documents,
    eligibility,
    extraction,
    health,
    observability,
    project_import,
    projects,
    retirement,
    stats,
    tenders,
    work_types,
)
from tender_intel.core.config import Settings, enforce_release_gates, get_settings
from tender_intel.core.container import Container
from tender_intel.infrastructure.downloader import HttpxDownloader
from tender_intel.infrastructure.observability.logging import configure_logging, get_logger
from tender_intel.infrastructure.observability.telemetry import init_sentry, init_tracing
from tender_intel.infrastructure.storage import LocalFileStorage
from tender_intel.infrastructure.workers.document_worker import (
    DocumentDownloadWorker,
    start_worker,
    stop_worker,
)
from tender_intel.infrastructure.workers.eligibility_workflow_worker import (
    EligibilityWorkflowWorker,
    start_workflow_worker,
    stop_workflow_worker,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    configure_logging(settings)
    enforce_release_gates(settings)
    init_sentry(settings)
    init_tracing(settings)
    log = get_logger(__name__)

    container = Container()
    container.settings.override(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("api.startup", environment=settings.environment.value, version=__version__)
        worker_task = None
        workflow_task = None
        if settings.enable_document_worker:
            worker = DocumentDownloadWorker(
                session_factory=container.session_factory(),
                downloader=HttpxDownloader(),
                storage=LocalFileStorage(settings.storage_dir),
                poll_seconds=settings.download_poll_seconds,
            )
            worker_task = start_worker(worker)
            workflow_task = start_workflow_worker(
                EligibilityWorkflowWorker(
                    session_factory=container.session_factory(),
                    settings=settings,
                    embeddings=container.embedding_provider(),
                    vectors=container.vector_store(),
                    poll_seconds=settings.download_poll_seconds,
                )
            )
        if settings.warm_embeddings_on_startup:
            await _warm_embeddings(container, settings)
        yield
        if workflow_task is not None:
            await stop_workflow_worker(workflow_task)
        if worker_task is not None:
            await stop_worker(worker_task)
        await container.engine().dispose()
        log.info("api.shutdown")

    app = FastAPI(
        title="Tender Intelligence Platform",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.container = container

    # Registered after CORS so it wraps it: Starlette applies middleware in
    # reverse order of registration, so the observability layer sits outermost
    # and observes the response CORS actually produced — including the status
    # code of a rejected preflight, which is exactly what an operator wants to
    # see when diagnosing a CORS fault.
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(tenders.router)
    app.include_router(documents.router)
    app.include_router(extraction.router)
    app.include_router(projects.router)
    app.include_router(project_import.router)
    app.include_router(retirement.router)
    app.include_router(stats.router)
    app.include_router(admin.router)
    app.include_router(eligibility.router)
    app.include_router(work_types.router)
    app.include_router(company_turnover.router)
    app.include_router(observability.router)

    _instrument_tracing(app, settings)
    return app


def _instrument_tracing(app: FastAPI, settings: Settings) -> None:
    """Add per-request OTel spans when an OTLP endpoint is configured."""
    if not settings.otel_exporter_otlp_endpoint:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
    except Exception as exc:
        get_logger(__name__).warning("tracing.instrument_failed", error=str(exc))


async def _warm_embeddings(container: Container, settings: Settings) -> None:
    """Load the embedding model and ensure the vector collection exists."""
    try:
        provider = container.embedding_provider()
        await provider.embed(["warmup"])  # triggers model load
        await container.vector_store().ensure_collection(
            settings.qdrant_collection, provider.dimension
        )
    except Exception as exc:
        get_logger(__name__).warning("embeddings.warm_failed", error=str(exc))


app = create_app()
