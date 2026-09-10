"""Decision orchestration (FR-300..FR-326).

Runs the eligibility screen, then risk, then recommendation, and advances the
tender to ANALYZED. The result is deterministic, so it is recomputed on demand
and never stored — only a recorded human verdict can go stale.

The screen replaces the retired qualification engine as the input to §13.3. Its
three-value verdict is carried through so rule 1 can tell a tender that failed
from one the screen could not decide.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from tender_intel.application.dto.decision import DecisionResult
from tender_intel.application.services.eligibility_service import EligibilityService
from tender_intel.application.services.matching_service import MatchingService
from tender_intel.domain.decision.eligibility import EligibilityResult
from tender_intel.domain.decision.models import (
    CompanyFinancials,
    FieldSignal,
    QualificationResult,
    QualificationRuleResult,
    RecommendationContext,
    RiskInput,
)
from tender_intel.domain.decision.recommendation import RecommendationEngine
from tender_intel.domain.decision.risk import RiskEngine
from tender_intel.domain.entities import AuditLog, TenderMetadata
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import DomainValidationError, EntityNotFoundError
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    TenderMetadataRepository,
    TenderRepository,
)
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.unknown import is_known
from tender_intel.infrastructure.extraction.parsing import parse_days

_ANALYSABLE = frozenset({TenderStatus.PARSED, TenderStatus.ANALYZED, TenderStatus.REVIEWED})

#: The similar-works rule is the one that names qualifying projects (FR-304).
_NAMES_PROJECTS = "technical_similar_works"


class DecisionService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        metadata_repo: TenderMetadataRepository,
        matching: MatchingService,
        eligibility: EligibilityService,
        audits: AuditLogRepository,
    ) -> None:
        self._tenders = tenders
        self._metadata_repo = metadata_repo
        self._matching = matching
        self._eligibility = eligibility
        self._audits = audits
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

        screen = await self._eligibility.compute(tender_id)
        qualification = self._to_qualification(screen)
        best_similarity, eligibility_supplied = await self._match_signal(tender_id, metadata)

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
                # §13.4's turnover buffer now reads the certified three-year
                # average the screen computed, not a configuration value.
                financials=CompanyFinancials(turnover=screen.financial.actual),
                best_match_similarity=best_similarity,
                eligibility_rules_supplied=eligibility_supplied,
                completion_period=self._signal(metadata, "completion_period"),
                emd=self._signal(metadata, "emd_amount"),
                tender_value=self._signal(metadata, "estimated_value"),
            ),
        )
        return DecisionResult(qualification=qualification, risk=risk, recommendation=recommendation)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_qualification(screen: EligibilityResult) -> QualificationResult:
        """Map the screen onto the shape §13.3 and the narrative already read.

        Each rule keeps its name, outcome, actual, required and reasoning, and
        the similar-works rule carries the first qualifying project by name so
        FR-304 is satisfied end to end.
        """
        named = screen.qualifying_projects[0] if screen.qualifying_projects else None
        rules = [
            QualificationRuleResult(
                name=rule.name,
                passed=rule.passed,
                detail=rule.detail,
                required=rule.required,
                actual=rule.actual,
                qualifying_project_id=(
                    named.project_id if named and rule.name == _NAMES_PROJECTS else None
                ),
                qualifying_project_name=(
                    named.name if named and rule.name == _NAMES_PROJECTS else None
                ),
            )
            for rule in screen.rules
        ]
        return QualificationResult(status=screen.status, rules=rules)

    async def _match_signal(
        self, tender_id: UUID, metadata: TenderMetadata | None
    ) -> tuple[Decimal | None, bool]:
        eligibility_supplied = bool(metadata and metadata.eligibility_criteria.is_known)
        result = await self._matching.match(tender_id, top_k=10)
        eligible = [c for c in result.candidates if c.eligible]
        best = max((c.similarity for c in eligible), default=None)
        return (Decimal(str(best)) if best is not None else None, eligibility_supplied)

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
                    "eligibility": result.qualification.status.value,
                    "win_probability": str(result.recommendation.win_probability),
                    "overall_risk": result.risk.overall_severity.value,
                },
            )
        )
