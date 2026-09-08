"""Tender registry routes (FR-101..FR-126)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from tender_intel.api.dependencies.auth import get_current_user, require_role
from tender_intel.api.dependencies.services import get_tender_service
from tender_intel.api.schemas.common import PageResponse
from tender_intel.api.schemas.tender import (
    BulkImportResponse,
    TenderCreateRequest,
    TenderPatchRequest,
    TenderResponse,
)
from tender_intel.application.services.tender_service import TenderService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest
from tender_intel.infrastructure.excel import parse_rows

router = APIRouter(prefix="/tenders", tags=["tenders"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TenderResponse)
async def create_tender(
    body: TenderCreateRequest,
    service: TenderService = Depends(get_tender_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> TenderResponse:
    tender = await service.create(body.to_dto(), actor_id=user.id)
    return TenderResponse.from_entity(tender)


@router.get("", response_model=PageResponse[TenderResponse])
async def list_tenders(
    service: TenderService = Depends(get_tender_service),
    _: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    status_filter: TenderStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
) -> PageResponse[TenderResponse]:
    page = await service.list(
        PageRequest(limit=limit, offset=offset), status=status_filter, search=search
    )
    return PageResponse.of(page, [TenderResponse.from_entity(t) for t in page.items])


@router.get("/{tender_id}", response_model=TenderResponse)
async def get_tender(
    tender_id: UUID,
    service: TenderService = Depends(get_tender_service),
    _: User = Depends(get_current_user),
) -> TenderResponse:
    return TenderResponse.from_entity(await service.get_or_404(tender_id))


@router.patch("/{tender_id}", response_model=TenderResponse)
async def patch_tender(
    tender_id: UUID,
    body: TenderPatchRequest,
    service: TenderService = Depends(get_tender_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> TenderResponse:
    tender = await service.patch(tender_id, body.to_dto(), actor_id=user.id)
    return TenderResponse.from_entity(tender)


@router.delete("/{tender_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tender(
    tender_id: UUID,
    service: TenderService = Depends(get_tender_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> Response:
    await service.delete(tender_id, actor_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/import", response_model=BulkImportResponse)
async def bulk_import(
    file: UploadFile = File(...),
    service: TenderService = Depends(get_tender_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> BulkImportResponse:
    content = await file.read()
    result = await service.bulk_import(parse_rows(content), actor_id=user.id)
    return BulkImportResponse.from_dto(result)
