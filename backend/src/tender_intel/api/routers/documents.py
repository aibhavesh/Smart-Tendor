"""Tender-document routes (FR-101..FR-126)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status

from tender_intel.api.dependencies.auth import get_current_user, require_role
from tender_intel.api.dependencies.services import get_document_service
from tender_intel.api.schemas.document import DocumentFromUrlRequest, DocumentResponse
from tender_intel.application.services.document_service import DocumentService
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole

router = APIRouter(tags=["documents"])


@router.post(
    "/tenders/{tender_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
async def add_document_from_url(
    tender_id: UUID,
    body: DocumentFromUrlRequest,
    service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> DocumentResponse:
    doc = await service.add_from_url(tender_id, body.source_url, actor_id=user.id)
    return DocumentResponse.from_entity(doc)


@router.post(
    "/tenders/{tender_id}/documents/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
async def upload_document(
    tender_id: UUID,
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> DocumentResponse:
    content = await file.read()
    doc = await service.upload(
        tender_id,
        filename=file.filename or "upload.bin",
        content=content,
        mime_type=file.content_type,
        actor_id=user.id,
    )
    return DocumentResponse.from_entity(doc)


@router.get("/tenders/{tender_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    tender_id: UUID,
    service: DocumentService = Depends(get_document_service),
    _: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    docs = await service.list_for_tender(tender_id)
    return [DocumentResponse.from_entity(d) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    service: DocumentService = Depends(get_document_service),
    _: User = Depends(get_current_user),
) -> DocumentResponse:
    return DocumentResponse.from_entity(await service.get_or_404(document_id))


@router.post("/documents/{document_id}/retrigger", response_model=DocumentResponse)
async def retrigger_document(
    document_id: UUID,
    service: DocumentService = Depends(get_document_service),
    user: User = Depends(require_role(UserRole.EMPLOYEE)),
) -> DocumentResponse:
    doc = await service.retrigger(document_id, actor_id=user.id)
    return DocumentResponse.from_entity(doc)
