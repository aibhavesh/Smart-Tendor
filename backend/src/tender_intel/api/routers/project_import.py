"""Bulk past-project import route.

Registered under ``/api/v1`` per the current convention for new routers. The
older past-project routes sit at ``/projects`` with no prefix; that divergence is
noted and left alone.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from tender_intel.api.dependencies.auth import require_role
from tender_intel.api.dependencies.services import get_project_import_service
from tender_intel.api.schemas.project_import import ProjectImportResponse
from tender_intel.application.services.project_import_service import ProjectImportService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/import", response_model=ProjectImportResponse)
async def bulk_import_projects(
    request: Request,
    files: list[UploadFile] = File(...),
    auto_tag: bool = Form(default=True),
    service: ProjectImportService = Depends(get_project_import_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> ProjectImportResponse:
    """Import many PDF or XLSX files in one operation.

    A file that fails is reported in its own entry and never aborts the batch.
    With ``auto_tag`` the stage A cascade links each imported project to the work
    types it confidently matches, which is what makes it count as eligibility
    evidence; without it every imported project needs tagging by hand before any
    eligibility screen will see it.
    """
    payload = [(f.filename or "upload", await f.read(), f.content_type) for f in files]
    result = await service.import_files(
        payload,
        auto_tag=auto_tag,
        actor_id=user.id,
        actor_role=user.role.value,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ProjectImportResponse.from_dto(result)
