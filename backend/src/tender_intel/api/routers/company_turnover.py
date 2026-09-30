"""Certified turnover routes (feature spec §2, §8).

MANAGER and above throughout, including the read: these are the company's own certified
financial figures, and unlike the taxonomy they are not operational reference
data every analyst needs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from tender_intel.api.dependencies.auth import require_role
from tender_intel.api.dependencies.services import (
    get_company_turnover_service,
    get_turnover_import_service,
)
from tender_intel.api.schemas.common import PageResponse
from tender_intel.api.schemas.work_type import (
    TurnoverCreateRequest,
    TurnoverExtractionResponse,
    TurnoverImportResponse,
    TurnoverPatchRequest,
    TurnoverResponse,
)
from tender_intel.application.services.company_turnover_service import CompanyTurnoverService
from tender_intel.application.services.turnover_import_service import TurnoverImportService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest

router = APIRouter(prefix="/api/v1/company-turnover", tags=["company-turnover"])


@router.post("/import", response_model=TurnoverImportResponse)
async def import_turnover_certificate(
    files: list[UploadFile] = File(..., description="PDF, XLSX, or XLSM turnover evidence"),
    service: TurnoverImportService = Depends(get_turnover_import_service),
    _: User = Depends(require_role(UserRole.MANAGER)),
) -> TurnoverImportResponse:
    """Extract candidate figures from temporary certificate uploads.

    This never writes financial data by itself.  The UI presents these candidates
    for confirmation and saves them through the audited turnover endpoints.
    """
    records: list[TurnoverExtractionResponse] = []
    warnings: list[str] = []
    for uploaded in files:
        filename = uploaded.filename or "turnover-evidence"
        content = await uploaded.read()
        if not content:
            warnings.append(f"{filename}: the uploaded file is empty.")
            continue
        result = await service.extract(filename=filename, content=content)
        records.extend(
            TurnoverExtractionResponse(
                financial_year=record.financial_year,
                contractual_turnover=record.contractual_turnover,
                source_file=record.source_file,
            )
            for record in result.records
        )
        warnings.extend(result.warnings)
    return TurnoverImportResponse(records=records, warnings=warnings)


@router.get("", response_model=PageResponse[TurnoverResponse])
async def list_turnover(
    service: CompanyTurnoverService = Depends(get_company_turnover_service),
    _: User = Depends(require_role(UserRole.MANAGER)),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PageResponse[TurnoverResponse]:
    page = await service.list(PageRequest(limit=limit, offset=offset))
    return PageResponse.of(page, [TurnoverResponse.from_entity(t) for t in page.items])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TurnoverResponse)
async def record_turnover(
    body: TurnoverCreateRequest,
    service: CompanyTurnoverService = Depends(get_company_turnover_service),
    actor: User = Depends(require_role(UserRole.MANAGER)),
) -> TurnoverResponse:
    created = await service.record(
        financial_year=body.financial_year.strip(),
        amount=body.contractual_turnover,
        certificate_document_id=body.certificate_document_id,
        actor_id=actor.id,
    )
    return TurnoverResponse.from_entity(created)


@router.patch("/{financial_year}", response_model=TurnoverResponse)
async def amend_turnover(
    financial_year: str,
    body: TurnoverPatchRequest,
    service: CompanyTurnoverService = Depends(get_company_turnover_service),
    actor: User = Depends(require_role(UserRole.MANAGER)),
) -> TurnoverResponse:
    updated = await service.amend(
        financial_year.strip(),
        amount=body.contractual_turnover,
        certificate_document_id=body.certificate_document_id,
        actor_id=actor.id,
    )
    return TurnoverResponse.from_entity(updated)
