"""SQLAlchemy tender-review repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities import TenderReview
from tender_intel.domain.enums.review import ReviewKind
from tender_intel.infrastructure.db.orm import TenderReviewModel
from tender_intel.infrastructure.repositories import mappers


class SqlAlchemyTenderReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, review: TenderReview) -> TenderReview:
        model = mappers.review_to_model(review)
        self._session.add(model)
        await self._session.flush()
        return mappers.review_to_domain(model)

    async def get(self, review_id: UUID) -> TenderReview | None:
        model = await self._session.get(TenderReviewModel, review_id)
        return mappers.review_to_domain(model) if model else None

    async def list_for_tender(self, tender_id: UUID) -> list[TenderReview]:
        stmt = (
            select(TenderReviewModel)
            .where(TenderReviewModel.tender_id == tender_id)
            .order_by(TenderReviewModel.created_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.review_to_domain(m) for m in rows]

    async def latest_verdict_at(self, tender_id: UUID) -> datetime | None:
        """When this tender was last decided, or None if it never was.

        A targeted aggregate rather than loading the history, because the
        staleness flag is read on every recommendation request.
        """
        stmt = select(func.max(TenderReviewModel.created_at)).where(
            TenderReviewModel.tender_id == tender_id,
            TenderReviewModel.kind == ReviewKind.VERDICT.value,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
