"""SQLAlchemy repositories for certified turnover, screen results and the
portfolio counter.

Grouped because all three exist only to serve the eligibility screen and are
always wired together.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.domain.entities.company_turnover import CompanyTurnover
from tender_intel.domain.entities.eligibility import (
    EligibilityNotification,
    TenderEligibility,
)
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.infrastructure.db.orm import (
    CompanyTurnoverModel,
    EligibilityNotificationModel,
    PastProjectModel,
    PortfolioVersionModel,
    TenderEligibilityModel,
    TenderEligibilityProjectModel,
    TenderEligibilityWorkTypeModel,
    WorkTypeModel,
)
from tender_intel.infrastructure.repositories import mappers

#: The counter is a single row. Deriving its id rather than generating one means
#: any process can find it without a lookup or a bootstrap migration.
_PORTFOLIO_ROW_ID = uuid5(UUID("00000000-0000-0000-0000-000000000000"), "portfolio_version")


class SqlAlchemyCompanyTurnoverRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: CompanyTurnover) -> CompanyTurnover:
        model = mappers.turnover_to_model(record)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.turnover_to_domain(model)

    async def get_by_year(self, financial_year: str) -> CompanyTurnover | None:
        stmt = select(CompanyTurnoverModel).where(
            CompanyTurnoverModel.financial_year == financial_year
        )
        model = (await self._session.execute(stmt)).scalars().first()
        return mappers.turnover_to_domain(model) if model else None

    async def list_for_years(self, labels: Sequence[str]) -> list[CompanyTurnover]:
        """Records for the requested years only.

        Returns fewer rows than asked for when a year has no certificate. The
        caller treats that shortfall as indeterminate rather than averaging over
        what happens to exist.
        """
        if not labels:
            return []
        stmt = select(CompanyTurnoverModel).where(
            CompanyTurnoverModel.financial_year.in_(list(labels))
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [mappers.turnover_to_domain(m) for m in rows]

    async def update(self, record: CompanyTurnover) -> CompanyTurnover:
        model = await self._session.get(CompanyTurnoverModel, record.id)
        if model is None:
            raise ValueError(f"turnover record {record.id} not found for update")
        mappers.turnover_apply(model, record)
        await self._session.flush()
        await self._session.refresh(model)
        return mappers.turnover_to_domain(model)

    # Declared last: naming a method ``list`` shadows the builtin for every
    # annotation that follows it in the class body.
    async def list(self, page: PageRequest) -> Page[CompanyTurnover]:
        total = (
            await self._session.execute(select(func.count(CompanyTurnoverModel.id)))
        ).scalar_one()
        stmt = (
            select(CompanyTurnoverModel)
            .order_by(CompanyTurnoverModel.financial_year.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return Page(
            items=[mappers.turnover_to_domain(m) for m in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )


class SqlAlchemyTenderEligibilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tender_id: UUID) -> TenderEligibility | None:
        model = await self._session.get(TenderEligibilityModel, tender_id)
        if model is None:
            return None
        matches = list(
            (
                await self._session.execute(
                    select(TenderEligibilityWorkTypeModel).where(
                        TenderEligibilityWorkTypeModel.tender_id == tender_id
                    )
                )
            )
            .scalars()
            .all()
        )
        projects = list(
            (
                await self._session.execute(
                    select(TenderEligibilityProjectModel).where(
                        TenderEligibilityProjectModel.tender_id == tender_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return mappers.eligibility_to_domain(
            model, matches, projects, codes=await self._labels(matches, projects)
        )

    async def upsert(self, record: TenderEligibility) -> TenderEligibility:
        """Replace the tender's result wholesale.

        The child rows are deleted and rewritten rather than diffed: a screen
        result is a snapshot of one evaluation, and merging two evaluations would
        produce a row describing neither.
        """
        model = await self._session.get(TenderEligibilityModel, record.tender_id)
        if model is None:
            model = TenderEligibilityModel()
            mappers.eligibility_apply(model, record)
            self._session.add(model)
        else:
            mappers.eligibility_apply(model, record)

        await self._session.flush()
        for table in (TenderEligibilityWorkTypeModel, TenderEligibilityProjectModel):
            await self._session.execute(delete(table).where(table.tender_id == record.tender_id))

        for match in record.matched_work_types:
            self._session.add(
                TenderEligibilityWorkTypeModel(
                    tender_id=record.tender_id,
                    work_type_id=match.work_type_id,
                    match_method=match.method.value,
                    match_score=match.score,
                    match_grade=match.grade.value,
                )
            )
        for project in record.qualifying_projects:
            self._session.add(
                TenderEligibilityProjectModel(
                    tender_id=record.tender_id,
                    project_id=project.project_id,
                    rank=project.rank,
                    work_value=project.work_value,
                )
            )
        await self._session.flush()
        return record

    async def _labels(
        self,
        matches: list[TenderEligibilityWorkTypeModel],
        projects: list[TenderEligibilityProjectModel],
    ) -> dict[UUID, str]:
        """Human-readable names for the stored ids, so a read reports codes."""
        labels: dict[UUID, str] = {}
        if matches:
            rows = (
                await self._session.execute(
                    select(WorkTypeModel.id, WorkTypeModel.code).where(
                        WorkTypeModel.id.in_([m.work_type_id for m in matches])
                    )
                )
            ).all()
            labels.update({row[0]: row[1] for row in rows})
        if projects:
            rows = (
                await self._session.execute(
                    select(PastProjectModel.id, PastProjectModel.name).where(
                        PastProjectModel.id.in_([p.project_id for p in projects])
                    )
                )
            ).all()
            labels.update({row[0]: row[1] for row in rows})
        return labels


class SqlAlchemyPortfolioVersionRepository:
    """The counter every portfolio mutation bumps.

    Created lazily on first read so no bootstrap migration has to seed it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current(self) -> int:
        model = await self._session.get(PortfolioVersionModel, _PORTFOLIO_ROW_ID)
        return int(model.counter) if model is not None else 0

    async def bump(self) -> int:
        model = await self._session.get(PortfolioVersionModel, _PORTFOLIO_ROW_ID)
        if model is None:
            model = PortfolioVersionModel(
                id=_PORTFOLIO_ROW_ID, counter=1, updated_at=datetime.now(UTC)
            )
            self._session.add(model)
        else:
            model.counter = int(model.counter) + 1
            model.updated_at = datetime.now(UTC)
        await self._session.flush()
        return int(model.counter)


class SqlAlchemyEligibilityNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: EligibilityNotification) -> EligibilityNotification:
        model = EligibilityNotificationModel(
            id=entry.id,
            tender_id=entry.tender_id,
            inputs_fingerprint=entry.inputs_fingerprint,
            status=entry.status.value,
            recipients=list(entry.recipients),
            sent_at=entry.sent_at,
        )
        self._session.add(model)
        await self._session.flush()
        return entry

    async def was_notified(self, tender_id: UUID, fingerprint: str) -> bool:
        """Has this exact result already been sent?

        Keyed on the fingerprint, so re-screening unchanged inputs is silent
        while a genuinely changed result notifies again.
        """
        stmt = select(EligibilityNotificationModel.id).where(
            EligibilityNotificationModel.tender_id == tender_id,
            EligibilityNotificationModel.inputs_fingerprint == fingerprint,
        )
        return (await self._session.execute(stmt)).first() is not None
