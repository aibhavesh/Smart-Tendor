"""AI Analyst report DTO."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from tender_intel.domain.enums.recommendation import RecommendationVerdict

# The five narrative sections (FR-330..FR-335).
SECTION_KEYS: tuple[str, ...] = (
    "executive_summary",
    "qualification_analysis",
    "risk_analysis",
    "win_probability_outlook",
    "recommended_actions",
)


@dataclass(frozen=True, slots=True)
class AnalystReport:
    tender_id: UUID
    # Carried verbatim from the deterministic decision — the narrative never
    # alters these (NFR-505).
    verdict: RecommendationVerdict
    win_probability: Decimal
    confidence: Decimal
    sections: dict[str, str]
    generated_by: str  # "gemini" | "offline"
