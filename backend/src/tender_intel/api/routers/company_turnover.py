"""Certified turnover routes (feature spec §2, §8).

ADMIN throughout, including the read: these are the company's own certified
financial figures, and unlike the taxonomy they are not operational reference
data every analyst needs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from tender_intel.api.dependencies.auth import require_role
from tender_intel.api.dependencies.services import get_company_turnover_service
from tender_intel.api.schemas.common import PageResponse
from tender_intel.api.schemas.work_type import (
    TurnoverCreateRequest,
    TurnoverPatchRequest,
    TurnoverResponse,
)
from tender_intel.application.services.company_turnover_service import CompanyTurnoverService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest

router = APIRouter(prefix="/api/v1/company-turnover", tags=["company-turnover"])


@router.get("", response_model=PageResponse[TurnoverResponse])
async def list_turnover(
    service: CompanyTurnoverService = Depends(get_company_turnover_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PageResponse[TurnoverResponse]:
    page = await service.list(PageRequest(limit=limit, offset=offset))
    return PageResponse.of(page, [TurnoverResponse.from_entity(t) for t in page.items])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TurnoverResponse)
async def record_turnover(
    body: TurnoverCreateRequest,
    service: CompanyTurnoverService = Depends(get_company_turnover_service),
    actor: User = Depends(require_role(UserRole.ADMIN)),
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
    actor: User = Depends(require_role(UserRole.ADMIN)),
) -> TurnoverResponse:
    updated = await service.amend(
        financial_year.strip(),
        amount=body.contractual_turnover,
        certificate_document_id=body.certificate_document_id,
        actor_id=actor.id,
    )
    return TurnoverResponse.from_entity(updated)
