"""Decision orchestration (FR-300..FR-326).

Gathers inputs for the deterministic engines (metadata, portfolio, company
financials, semantic-match similarity), runs qualification -> risk ->
recommendation, and advances the tender to ANALYZED. The result is deterministic,
so it is recomputed on demand (the AI Analyst in Phase 7 narrates it verbatim).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from tender_intel.application.dto.decision import DecisionResult
from tender_intel.application.services.matching_service import MatchingService
from tender_intel.core.config import Settings
from tender_intel.domain.decision import thresholds as th
from tender_intel.domain.decision.models import (
    CompanyFinancials,
    FieldSignal,
    QualificationInput,
    RecommendationContext,
    RiskInput,
    SimilarWork,
)
from tender_intel.domain.decision.qualification import QualificationEngine
from tender_intel.domain.decision.recommendation import RecommendationEngine
from tender_intel.domain.decision.risk import RiskEngine
from tender_intel.domain.entities import AuditLog, TenderMetadata
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import DomainValidationError, EntityNotFoundError
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    PastProjectRepository,
    TenderMetadataRepository,
    TenderRepository,
)
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest
from tender_intel.domain.value_objects.unknown import is_known
from tender_intel.infrastructure.extraction.constraints import parse_min_value
from tender_intel.infrastructure.extraction.parsing import parse_days

_ANALYSABLE = frozenset({TenderStatus.PARSED, TenderStatus.ANALYZED, TenderStatus.REVIEWED})


class DecisionService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        metadata_repo: TenderMetadataRepository,
        projects: PastProjectRepository,
        matching: MatchingService,
        audits: AuditLogRepository,
        settings: Settings,
    ) -> None:
        self._tenders = tenders
        self._metadata_repo = metadata_repo
        self._projects = projects
        self._matching = matching
        self._audits = audits
        self._financials = CompanyFinancials(
            turnover=settings.company_turnover, net_worth=settings.company_net_worth
        )
        self._qualification = QualificationEngine()
        self._risk = RiskEngine()
        self._recommendation = RecommendationEngine()

    async def analyze(self, tender_id: UUID, *, actor_id: UUID | None = None) -> DecisionResult:
        result = await self.compute(tender_id)
        await self._advance_to_analyzed(tender_id)
        await self._audit(actor_id, tender_id, result)
        return result

    async def compute(self, tender_id: UUID) -> DecisionResult:
        """Run the engines without mutating tender state (pure recompute)."""
        tender = await self._tenders.get(tender_id)
        if tender is None:
            raise EntityNotFoundError("Tender", tender_id)
        if tender.status not in _ANALYSABLE:
            raise DomainValidationError("tender must be extracted (PARSED) before analysis")

        metadata = await self._metadata_repo.get_for_tender(tender_id)
        estimated_value = self._estimated_value(metadata, tender.estimated_value)
        works = await self._similar_works()
        best_similarity, eligibility_supplied = await self._match_signal(tender_id, metadata)

        qualification = self._qualification.evaluate(
            QualificationInput(
                estimated_value=estimated_value,
                similar_works=works,
                financials=self._financials,
                required_work_value=self._required_work_value(metadata),
                work_value_required_pct=th.WORK_VALUE_REQUIRED_PCT_DEFAULT,
            )
        )
        risk = self._risk.assess(
            RiskInput(
                estimated_value=estimated_value,
                emd_amount=self._decimal(metadata, "emd_amount"),
                completion_days=self._completion_days(metadata),
                clause_text=self._clause_text(metadata),
            )
        )
        recommendation = self._recommendation.recommend(
            qualification,
            risk,
            RecommendationContext(
                estimated_value=estimated_value,
                financials=self._financials,
                best_match_similarity=best_similarity,
                eligibility_rules_supplied=eligibility_supplied,
                completion_period=self._signal(metadata, "completion_period"),
                emd=self._signal(metadata, "emd_amount"),
                tender_value=self._signal(metadata, "estimated_value"),
            ),
        )
        return DecisionResult(qualification=qualification, risk=risk, recommendation=recommendation)

    # ------------------------------------------------------------------ #
    async def _similar_works(self) -> list[SimilarWork]:
        page = await self._projects.list(PageRequest(limit=MAX_LIMIT))
        return [
            SimilarWork(project_id=p.id, name=p.name, value=p.work_value)
            for p in page.items
            if p.work_value is not None
        ]

    async def _match_signal(
        self, tender_id: UUID, metadata: TenderMetadata | None
    ) -> tuple[Decimal | None, bool]:
        eligibility_supplied = bool(metadata and metadata.eligibility_criteria.is_known)
        result = await self._matching.match(tender_id, top_k=10)
        eligible = [c for c in result.candidates if c.eligible]
        best = max((c.similarity for c in eligible), default=None)
        return (Decimal(str(best)) if best is not None else None, eligibility_supplied)

    def _required_work_value(self, metadata: TenderMetadata | None) -> Decimal | None:
        if metadata is None or not metadata.eligibility_criteria.is_known:
            return None
        return parse_min_value(str(metadata.eligibility_criteria.value))

    @staticmethod
    def _estimated_value(
        metadata: TenderMetadata | None, fallback: Decimal | None
    ) -> Decimal | None:
        if metadata is not None and is_known(metadata.estimated_value.value):
            value = metadata.estimated_value.value
            if isinstance(value, Decimal):
                return value
        return fallback

    @staticmethod
    def _decimal(metadata: TenderMetadata | None, field: str) -> Decimal | None:
        if metadata is None:
            return None
        value = getattr(metadata, field).value
        return value if is_known(value) and isinstance(value, Decimal) else None

    @staticmethod
    def _completion_days(metadata: TenderMetadata | None) -> int | None:
        if metadata is None or not metadata.completion_period.is_known:
            return None
        return parse_days(str(metadata.completion_period.value))

    @staticmethod
    def _signal(metadata: TenderMetadata | None, field: str) -> FieldSignal:
        if metadata is None:
            return FieldSignal(known=False, confidence=Decimal("0"))
        extracted: ExtractedField[object] = getattr(metadata, field)
        return FieldSignal(known=extracted.is_known, confidence=Decimal(str(extracted.confidence)))

    @staticmethod
    def _clause_text(metadata: TenderMetadata | None) -> str:
        if metadata is None:
            return ""
        parts = []
        for name in ("eligibility_criteria", "scope_of_work"):
            field = getattr(metadata, name)
            if field.is_known:
                parts.append(str(field.value))
        parts.append(metadata.raw_text)
        return "\n".join(parts)

    async def _advance_to_analyzed(self, tender_id: UUID) -> None:
        tender = await self._tenders.get(tender_id)
        if tender is not None and tender.status.can_transition_to(TenderStatus.ANALYZED):
            tender.transition_to(TenderStatus.ANALYZED)
            await self._tenders.update(tender)

    async def _audit(self, actor_id: UUID | None, tender_id: UUID, result: DecisionResult) -> None:
        await self._audits.add(
            AuditLog(
                action="tender.analyze",
                entity_type="Tender",
                entity_id=str(tender_id),
                actor_id=actor_id,
                diff={
                    "verdict": result.recommendation.verdict.value,
                    "win_probability": str(result.recommendation.win_probability),
                    "overall_risk": result.risk.overall_severity.value,
                },
            )
        )
