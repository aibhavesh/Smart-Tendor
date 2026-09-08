"""Frontend log-ingestion endpoint (FR-706).

Accepts a bounded batch of client-side log entries and re-emits them through the
server's structured logger so browser diagnostics land in the same pipeline.

**This endpoint is deliberately open to anonymous callers**, and that is a
considered decision rather than an oversight. The browser errors most worth
capturing happen on the landing and sign-in screens — a failed sign-in, a broken
bundle, a blocked Google script — where by definition nobody holds a token yet.
Requiring authentication would blind exactly the window that matters most.

What that leaves is not "unprotected" but "protected by something other than a
bearer token":

* **Attribution.** A valid token is used when present, so entries from a real
  session carry the user id and can be told apart from anonymous noise.
* **Rate limiting.** Per user, or per client address when anonymous. This is
  what stops the endpoint being an unbounded write amplifier.
* **Bounded payloads.** Every field is capped in the schema, including the
  free-form ``context`` bag.
* **A kill switch.** ``ENABLE_FRONTEND_LOGS=false`` closes it entirely.

The limiter is per worker process and keyed on the socket address, so it bounds
cost rather than guaranteeing a quota. It is not a security boundary and must
not be relied on as one — see ``infrastructure/observability/rate_limit.py``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from tender_intel.api.dependencies.auth import get_optional_subject
from tender_intel.api.dependencies.db import get_app_settings
from tender_intel.api.schemas.observability import FrontendLogBatch, LogIngestResponse
from tender_intel.core.config import Settings
from tender_intel.infrastructure.observability.logging import get_logger
from tender_intel.infrastructure.observability.rate_limit import FixedWindowRateLimiter

router = APIRouter(tags=["observability"])
_log = get_logger("frontend")


def _limiter(request: Request, limit: int) -> FixedWindowRateLimiter:
    """One limiter per application instance, held on ``app.state``.

    Not a module global: two apps in one process (every test that builds its own)
    would otherwise share counters, and one test's traffic would throttle another.
    """
    existing = getattr(request.app.state, "frontend_log_limiter", None)
    if existing is None:
        existing = FixedWindowRateLimiter(limit=limit, window_seconds=60.0)
        request.app.state.frontend_log_limiter = existing
    return existing


def _client_key(request: Request, user_id: UUID | None) -> str:
    """Who to charge the batch to.

    A signed-in user is keyed by id, so one person on a flaky office network is
    not throttled by a colleague sharing the egress address. Anonymous callers
    fall back to the socket address — note that behind a reverse proxy this is
    the proxy, which collapses every anonymous client into one bucket. Trusting
    ``X-Forwarded-For`` instead would be worse: it is caller-supplied, so it
    would let anyone defeat the limit by varying a header.
    """
    if user_id is not None:
        return f"user:{user_id}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


@router.post("/observability/logs", status_code=status.HTTP_202_ACCEPTED)
async def ingest_frontend_logs(
    batch: FrontendLogBatch,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    user_id: UUID | None = Depends(get_optional_subject),
) -> LogIngestResponse:
    if not settings.enable_frontend_logs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="log ingestion disabled")

    # Charged per entry, not per request: the entries are what reach the log
    # pipeline, and a batch may carry a hundred of them.
    allowed, retry_after = _limiter(request, settings.frontend_log_entries_per_minute).check(
        _client_key(request, user_id), cost=len(batch.logs)
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many log entries. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    client = request.client.host if request.client else None
    for entry in batch.logs:
        emit = getattr(_log, entry.level)
        emit(
            "frontend.log",
            client_message=entry.message,
            context=entry.context,
            url=entry.url,
            client_timestamp=entry.timestamp,
            client_ip=client,
            # Marked on every entry so anonymous input is filterable downstream
            # rather than indistinguishable from a real session.
            user_id=str(user_id) if user_id else None,
            authenticated=user_id is not None,
        )
    return LogIngestResponse(received=len(batch.logs))
