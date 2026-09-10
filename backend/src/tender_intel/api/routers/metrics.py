"""Prometheus metrics endpoint (FR-701).

Credential-protected (HTTP Basic) and config-switchable via ``metrics_enabled``.
Exposes the application registry in the Prometheus text exposition format.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from tender_intel.api.dependencies.db import get_app_settings
from tender_intel.core.config import Settings
from tender_intel.infrastructure.observability.telemetry import REGISTRY

router = APIRouter(tags=["observability"])
_basic = HTTPBasic(auto_error=False)


def _authorised(credentials: HTTPBasicCredentials | None, settings: Settings) -> bool:
    if credentials is None:
        return False
    user_ok = secrets.compare_digest(credentials.username, settings.metrics_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.metrics_password)
    return user_ok and pass_ok


@router.get("/metrics")
async def metrics(
    settings: Settings = Depends(get_app_settings),
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> Response:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="metrics disabled")
    if not _authorised(credentials, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorised",
            headers={"WWW-Authenticate": "Basic"},
        )
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
