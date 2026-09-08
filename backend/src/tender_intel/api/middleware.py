"""HTTP middleware: per-request structured-log binding and Prometheus metrics."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from tender_intel.infrastructure.observability.telemetry import (
    http_request_duration_seconds,
    http_requests_total,
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        # Use the route template (not the raw path) as the metric label to bound
        # cardinality; falls back to the literal path before routing resolves.
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed = time.perf_counter() - start
        route = request.scope.get("route")
        label_path = getattr(route, "path", "unmatched")
        http_request_duration_seconds.labels(request.method, label_path).observe(elapsed)
        http_requests_total.labels(request.method, label_path, response.status_code).inc()
        response.headers["x-request-id"] = request_id
        return response
