"""Observability routes: browser log ingestion and Prometheus metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from tender_intel.api.dependencies.db import get_app_settings
from tender_intel.api.schemas.observability import FrontendLogBatch, LogIngestResponse
from tender_intel.core.config import Settings
from tender_intel.infrastructure.observability.logging import get_logger
from tender_intel.infrastructure.observability.rate_limit import FixedWindowRateLimiter
from tender_intel.infrastructure.observability.telemetry import generate_latest

router = APIRouter(tags=["observability"])

_log = get_logger(__name__)
_basic = HTTPBasic(auto_error=False)


def _build_limiter(settings: Settings) -> FixedWindowRateLimiter:
    """One limiter per app instance, sized from that instance's settings.

    Deliberately not a module-level singleton: a cached limiter would capture the
    first app's budget and silently serve it to every app built afterwards in the
    same process. Tests build several apps with different limits, and so does a
    process that reloads settings. Per process, not shared across workers — see
    FixedWindowRateLimiter for what that does and does not guarantee.
    """
    return FixedWindowRateLimiter(limit=settings.frontend_log_entries_per_minute)


@router.post(
    "/observability/logs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=LogIngestResponse,
)
async def ingest_logs(
    batch: FrontendLogBatch,
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> LogIngestResponse:
    """Accept a batch of browser diagnostics and re-emit it as server logs.

    Unauthenticated by necessity: the errors worth capturing happen on the
    landing and sign-in screens, before anyone holds a token. The rate limit is
    what keeps that from becoming an open write amplifier, and it is charged per
    *entry* rather than per request so a large batch cannot buy itself through.
    """
    if not settings.enable_frontend_logs:
        # 404, not 403: the browser client treats this as "feature off" and
        # disables itself, which is the correct reading of a deliberate default.
        raise HTTPException(status_code=404, detail="Frontend log ingestion is disabled.")

    # Stored on app.state rather than in a module global, so the window state
    # survives across requests (that is the point) without leaking between apps.
    limiter: FixedWindowRateLimiter | None = getattr(request.app.state, "log_limiter", None)
    if limiter is None:
        limiter = _build_limiter(settings)
        request.app.state.log_limiter = limiter

    subject = getattr(request.state, "subject_id", None)
    # Behind the shipped nginx every anonymous caller shares the proxy's socket
    # address, so this collapses to one bucket. Documented, and not a security
    # boundary — see FixedWindowRateLimiter.
    client = request.client.host if request.client else "unknown"
    key = f"user:{subject}" if subject else f"addr:{client}"

    allowed, retry_after = limiter.check(key, cost=len(batch.logs))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Log ingestion rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )

    for entry in batch.logs:
        _log.warning(
            "frontend.log",
            level=entry.level,
            message=entry.message,
            url=entry.url,
            client_timestamp=entry.timestamp,
            **(entry.context or {}),
        )

    return LogIngestResponse(received=len(batch.logs))


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(
    response: Response,
    settings: Settings = Depends(get_app_settings),
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> Response:
    """Prometheus exposition, behind Basic Auth with its own credentials.

    Kept separate from ``METRICS_ENABLED``-style application auth because the
    scrape target is a machine, not a signed-in user. Returns 404 when disabled
    so a disabled endpoint is indistinguishable from one that was never built.
    """
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics are disabled.")

    unauthenticated = (
        credentials is None
        or credentials.username != settings.metrics_user
        or credentials.password != settings.metrics_password
    )
    if unauthenticated:
        # `basic` rather than `auto_error` so the challenge is ours to shape, and
        # so a wrong password gets the same answer as no password.
        raise HTTPException(
            status_code=401,
            detail="Invalid metrics credentials.",
            headers={"WWW-Authenticate": 'Basic realm="metrics"'},
        )

    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")
