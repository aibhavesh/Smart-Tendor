"""Liveness and readiness endpoints.

``/health`` is unauthenticated and cheap — intended for load balancers. Deeper
component health (DB, Qdrant, host resources) is exposed via the admin surface
in Phase 9.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from tender_intel import __version__

    return HealthResponse(status="ok", version=__version__)
