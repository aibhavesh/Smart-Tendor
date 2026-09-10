"""AI Analyst narrative layer (FR-330..FR-335).

Generates the five narrative sections from the *already-computed* deterministic
decision. On any LLM failure or malformed output it falls back to a deterministic
offline generator, so the report endpoint never fails (NFR-405). The verdict,
win probability and confidence are always carried verbatim from the decision.
"""

from __future__ import annotations

from uuid import UUID

from tender_intel.application.dto.analyst import AnalystReport
from tender_intel.application.services.analyst_narrative import (
    build_offline_sections,
    build_prompt,
    validate_sections,
)
from tender_intel.application.services.decision_service import DecisionService
from tender_intel.domain.exceptions import EntityNotFoundError
from tender_intel.domain.interfaces.providers import LLMProvider
from tender_intel.domain.interfaces.repositories import TenderRepository
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)


class AnalystService:
    def __init__(
        self,
        *,
        decision: DecisionService,
        tenders: TenderRepository,
        llm: LLMProvider,
    ) -> None:
        self._decision = decision
        self._tenders = tenders
        self._llm = llm

    async def generate_report(self, tender_id: UUID) -> AnalystReport:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            raise EntityNotFoundError("Tender", tender_id)
        # Raises DomainValidationError if the tender is not yet extracted.
        decision = await self._decision.compute(tender_id)

        system, prompt, schema = build_prompt(tender.title, decision)
        generated_by = "gemini"
        try:
            raw = await self._llm.generate_json(system=system, prompt=prompt, schema=schema)
            sections = validate_sections(raw)
        except Exception as exc:
            _log.warning("analyst.fallback", tender_id=str(tender_id), error=str(exc))
            sections = build_offline_sections(tender.title, decision)
            generated_by = "offline"

        rec = decision.recommendation
        return AnalystReport(
            tender_id=tender_id,
            verdict=rec.verdict,  # verbatim from the deterministic engine
            win_probability=rec.win_probability,
            confidence=rec.confidence,
            sections=sections,
            generated_by=generated_by,
        )
