"""Certified turnover administration (feature spec §2, §8).

ADMIN only, one record per financial year, every mutation audited. These figures
decide the financial criterion for every tender at once, so a wrong entry is not
a local error.

No portfolio-counter bump here. The counter tracks the *portfolio* — projects,
work types, aliases and tags. Turnover reaches the fingerprint directly, as the
set of per-year figures the evaluation read, so a changed figure invalidates
without the counter moving.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from tender_intel.domain.entities import AuditLog
from tender_intel.domain.entities.company_turnover import CompanyTurnover
from tender_intel.domain.exceptions import DuplicateEntityError, EntityNotFoundError
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    CompanyTurnoverRepository,
)
from tender_intel.domain.services.financial_year import parse_label
from tender_intel.domain.value_objects.pagination import Page, PageRequest


class CompanyTurnoverService:
    def __init__(
        self,
        *,
        turnover: CompanyTurnoverRepository,
        audits: AuditLogRepository,
    ) -> None:
        self._turnover = turnover
        self._audits = audits

    async def record(
        self,
        *,
        financial_year: str,
        amount: Decimal,
        certificate_document_id: UUID | None,
        actor_id: UUID,
    ) -> CompanyTurnover:
        # Raises on a malformed label before anything is written, so a bad year
        # can never reach the averaging window.
        parse_label(financial_year)
        if await self._turnover.get_by_year(financial_year) is not None:
            raise DuplicateEntityError("CompanyTurnover", "financial_year", financial_year)

        created = await self._turnover.add(
            CompanyTurnover(
                financial_year=financial_year,
                contractual_turnover=amount,
                certificate_document_id=certificate_document_id,
                recorded_by=actor_id,
            )
        )
        await self._audit(
            actor_id,
            "company_turnover.record",
            created.id,
            {"financial_year": financial_year, "amount": str(amount)},
        )
        return created

    async def list(self, page: PageRequest) -> Page[CompanyTurnover]:
        return await self._turnover.list(page)

    async def amend(
        self,
        financial_year: str,
        *,
        amount: Decimal | None,
        certificate_document_id: UUID | None,
        actor_id: UUID,
    ) -> CompanyTurnover:
        record = await self._turnover.get_by_year(financial_year)
        if record is None:
            raise EntityNotFoundError("CompanyTurnover", financial_year)

        diff: dict[str, object] = {}
        if amount is not None and amount != record.contractual_turnover:
            diff["amount"] = {
                "before": str(record.contractual_turnover),
                "after": str(amount),
            }
            record.contractual_turnover = amount
        if certificate_document_id is not None:
            diff["certificate_document_id"] = {
                "before": str(record.certificate_document_id or ""),
                "after": str(certificate_document_id),
            }
            record.certificate_document_id = certificate_document_id
        if not diff:
            return record

        record.recorded_by = actor_id
        updated = await self._turnover.update(record)
        await self._audit(actor_id, "company_turnover.amend", record.id, diff)
        return updated

    async def _audit(
        self, actor_id: UUID, action: str, entity_id: UUID, diff: dict[str, object]
    ) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type="CompanyTurnover",
                entity_id=str(entity_id),
                actor_id=actor_id,
                diff=diff,
            )
        )
