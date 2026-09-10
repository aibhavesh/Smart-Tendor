"""Extraction routes: run extraction and read metadata / BOQ / analytics."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from tender_intel.api.dependencies.auth import get_current_user, require_role
from tender_intel.api.dependencies.repositories import get_boq_repo, get_tender_metadata_repo
from tender_intel.api.dependencies.services import get_extraction_service, get_tender_service
from tender_intel.api.schemas.extraction import (
    BOQAnalyticsResponse,
    BOQItemResponse,
    ExtractionResponse,
    MetadataResponse,
)
from tender_intel.application.services.boq_analytics import summarise
from tender_intel.application.services.extraction_service import ExtractionService
from tender_intel.application.services.tender_service import TenderService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.exceptions import EntityNotFoundError
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyBOQItemRepository,
    SqlAlchemyTenderMetadataRepository,
)

router = APIRouter(prefix="/tenders/{tender_id}", tags=["extraction"])


@router.post("/extract", response_model=ExtractionResponse)
async def extract(
    tender_id: UUID,
    document_id: UUID | None = Query(default=None),
    service: ExtractionService = Depends(get_extraction_service),
    tenders: TenderService = Depends(get_tender_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> ExtractionResponse:
    result = await service.extract(tender_id, document_id=document_id, actor_id=user.id)
    tender = await tenders.get_or_404(tender_id)
    return ExtractionResponse(
        tender_id=tender_id,
        status=tender.status.value,
        metadata=MetadataResponse.from_entity(result.metadata),
        boq_item_count=len(result.boq_items),
    )


@router.get("/metadata", response_model=MetadataResponse)
async def get_metadata(
    tender_id: UUID,
    repo: SqlAlchemyTenderMetadataRepository = Depends(get_tender_metadata_repo),
    _: User = Depends(get_current_user),
) -> MetadataResponse:
    metadata = await repo.get_for_tender(tender_id)
    if metadata is None:
        raise EntityNotFoundError("TenderMetadata", tender_id)
    return MetadataResponse.from_entity(metadata)


@router.get("/boq", response_model=list[BOQItemResponse])
async def get_boq(
    tender_id: UUID,
    repo: SqlAlchemyBOQItemRepository = Depends(get_boq_repo),
    _: User = Depends(get_current_user),
) -> list[BOQItemResponse]:
    items = await repo.list_for_tender(tender_id)
    return [BOQItemResponse.from_entity(i) for i in items]


@router.get("/boq/analytics", response_model=BOQAnalyticsResponse)
async def get_boq_analytics(
    tender_id: UUID,
    repo: SqlAlchemyBOQItemRepository = Depends(get_boq_repo),
    _: User = Depends(get_current_user),
) -> BOQAnalyticsResponse:
    items = await repo.list_for_tender(tender_id)
    return BOQAnalyticsResponse.from_dto(summarise(items))
