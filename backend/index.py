"""Vercel entrypoint for the Tender Intelligence FastAPI application.

The standalone backend repository is the Vercel project root. Export the
FastAPI instance for framework detection, and accept both native routes
(``/health``) and the legacy ``/api`` prefix (``/api/health``).
"""

from __future__ import annotations

import os
import sys
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_SRC = os.path.join(ROOT, "src")
if BACKEND_SRC not in sys.path:
    sys.path.insert(0, BACKEND_SRC)

# Serverless functions must not rely on a long-running background worker or
# startup embedding warmup.
os.environ.setdefault("ENABLE_DOCUMENT_WORKER", "false")
os.environ.setdefault("WARM_EMBEDDINGS_ON_STARTUP", "false")

from tender_intel.api.app import app as _application  # noqa: E402


class StripVercelApiPrefix:
    """Forward /api/* requests to the existing FastAPI routes as /*."""

    def __init__(self, app: Any) -> None:
        self.application = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        if scope["type"] in {"http", "websocket"}:
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                scope = dict(scope)
                scope["path"] = path[4:] or "/"

                raw_path = scope.get("raw_path")
                if raw_path:
                    raw = bytes(raw_path)
                    if raw == b"/api" or raw.startswith(b"/api/"):
                        scope["raw_path"] = raw[4:] or b"/"

                scope["root_path"] = "/api"

        return await self.application(scope, receive, send)


_application.add_middleware(StripVercelApiPrefix)
app = _application
