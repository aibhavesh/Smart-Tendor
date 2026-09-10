"""SQLAlchemy repositories for tenders, documents, metadata and BOQ items."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities import BOQItem, Tender, TenderDocument, TenderMetadata
from tender_intel.domain.enums.document_status import DocumentStatus
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.infrastructure.db.orm import (
    BOQItemModel,
    TenderDocumentModel,
    TenderMetadataModel,
    TenderModel,
)
from tender_intel.infrastructure.repositories import mappers


class SqlAlchemyTenderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tender: Tender) -> Tender:
        model = mappers.tender_to_model(tender)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.tender_to_domain(model)

    async def get(self, tender_id: UUID) -> Tender | None:
        model = await self._session.get(TenderModel, tender_id)
        return mappers.tender_to_domain(model) if model else None

    async def get_by_number(self, tender_number: str) -> Tender | None:
        stmt = select(TenderModel).where(TenderModel.tender_number == tender_number)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.tender_to_domain(model) if model else None

    async def exists_number(self, tender_number: str) -> bool:
        stmt = select(func.count(TenderModel.id)).where(TenderModel.tender_number == tender_number)
        return bool((await self._session.execute(stmt)).scalar_one())

    async def list(
        self,
        page: PageRequest,
        *,
        status: TenderStatus | None = None,
        search: str | None = None,
    ) -> Page[Tender]:
        conditions = []
        if status is not None:
            conditions.append(TenderModel.status == status.value)
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(TenderModel.title.ilike(like), TenderModel.tender_number.ilike(like))
            )
        count_stmt = select(func.count(TenderModel.id))
        list_stmt = select(TenderModel).order_by(TenderModel.created_at.desc())
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
            list_stmt = list_stmt.where(cond)
        total = (await self._session.execute(count_stmt)).scalar_one()
        rows = (
            (await self._session.execute(list_stmt.limit(page.limit).offset(page.offset)))
            .scalars()
            .all()
        )
        return Page(
            items=[mappers.tender_to_domain(m) for m in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def update(self, tender: Tender) -> Tender:
        model = await self._session.get(TenderModel, tender.id)
        if model is None:
            raise ValueError(f"tender {tender.id} not found for update")
        mappers.tender_apply(model, tender)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.tender_to_domain(model)

    async def delete(self, tender_id: UUID) -> None:
        model = await self._session.get(TenderModel, tender_id)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()


class SqlAlchemyTenderDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: TenderDocument) -> TenderDocument:
        model = mappers.document_to_model(document)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.document_to_domain(model)

    async def get(self, document_id: UUID) -> TenderDocument | None:
        model = await self._session.get(TenderDocumentModel, document_id)
        return mappers.document_to_domain(model) if model else None

    async def list_for_tender(self, tender_id: UUID) -> list[TenderDocument]:
        stmt = (
            select(TenderDocumentModel)
            .where(TenderDocumentModel.tender_id == tender_id)
            .order_by(TenderDocumentModel.created_at.asc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.document_to_domain(m) for m in rows]

    async def list_by_status(self, status: DocumentStatus, limit: int) -> list[TenderDocument]:
        stmt = (
            select(TenderDocumentModel)
            .where(TenderDocumentModel.status == status.value)
            .order_by(TenderDocumentModel.created_at.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.document_to_domain(m) for m in rows]

    async def update(self, document: TenderDocument) -> TenderDocument:
        model = await self._session.get(TenderDocumentModel, document.id)
        if model is None:
            raise ValueError(f"document {document.id} not found for update")
        mappers.document_apply(model, document)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.document_to_domain(model)


class SqlAlchemyTenderMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_tender(self, tender_id: UUID) -> TenderMetadata | None:
        stmt = select(TenderMetadataModel).where(TenderMetadataModel.tender_id == tender_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return mappers.metadata_to_domain(model) if model else None

    async def upsert(self, metadata: TenderMetadata) -> TenderMetadata:
        stmt = select(TenderMetadataModel).where(
            TenderMetadataModel.tender_id == metadata.tender_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            model = mappers.metadata_to_model(metadata)
            self._session.add(model)
        else:
            mappers.metadata_apply(model, metadata)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.metadata_to_domain(model)


class SqlAlchemyBOQItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, items: list[BOQItem]) -> list[BOQItem]:
        models = [mappers.boq_to_model(i) for i in items]
        self._session.add_all(models)
        await self._session.flush()
        return [mappers.boq_to_domain(m) for m in models]

    async def list_for_tender(self, tender_id: UUID) -> list[BOQItem]:
        stmt = select(BOQItemModel).where(BOQItemModel.tender_id == tender_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.boq_to_domain(m) for m in rows]

    async def delete_for_tender(self, tender_id: UUID) -> None:
        await self._session.execute(delete(BOQItemModel).where(BOQItemModel.tender_id == tender_id))
        await self._session.flush()
