"""Phase 7 AI-Analyst narrative tests: schema, validation, offline fallback."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender_intel.application.dto.analyst import SECTION_KEYS
from tender_intel.application.dto.decision import DecisionResult
from tender_intel.application.services.analyst_narrative import (
    RESPONSE_SCHEMA,
    build_offline_sections,
    build_prompt,
    validate_sections,
)
from tender_intel.domain.decision.models import (
    QualificationResult,
    QualificationRuleResult,
    Recommendation,
    RiskAssessment,
    RiskCategoryResult,
)
from tender_intel.domain.enums.recommendation import RecommendationVerdict
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel


def _decision() -> DecisionResult:
    qual = QualificationResult(
        qualified=True,
        rules=[
            QualificationRuleResult("work_value", True, "highest work meets requirement"),
            QualificationRuleResult("average_annual_turnover", True, "turnover ok"),
            QualificationRuleResult("net_worth", True, "net worth non-negative"),
        ],
    )
    risk = RiskAssessment(
        categories=[
            RiskCategoryResult(RiskCategory.HIGH_EMD, RiskLevel.LOW, Decimal("2.0"), ["EMD 1%"]),
            RiskCategoryResult(
                RiskCategory.PERFORMANCE_GUARANTEE, RiskLevel.MEDIUM, Decimal("5.0"), ["PG 7%"]
            ),
        ],
        overall_severity=RiskLevel.MEDIUM,
        overall_score=Decimal("5.0"),
        overall_category=RiskCategory.PERFORMANCE_GUARANTEE,
    )
    rec = Recommendation(
        verdict=RecommendationVerdict.REVIEW,
        win_probability=Decimal("62.5"),
        confidence=Decimal("0.8"),
        pros=["Strong turnover"],
        cons=["Performance guarantee exposure"],
        document_checklist=["EMD proof", "PAN card"],
        applied_rules=["rule_4a_mid_match_review"],
    )
    return DecisionResult(qualification=qual, risk=risk, recommendation=rec)


# --- Schema / prompt ---
def test_schema_requires_five_string_sections():
    assert set(RESPONSE_SCHEMA["required"]) == set(SECTION_KEYS)
    assert all(RESPONSE_SCHEMA["properties"][k]["type"] == "string" for k in SECTION_KEYS)


def test_build_prompt_includes_facts_and_fixed_numbers():
    system, prompt, schema = build_prompt("Road work", _decision())
    assert "must NOT change" in system
    assert "Road work" in prompt
    assert "62.5" in prompt  # win probability passed as a fact
    assert schema is RESPONSE_SCHEMA


# --- Validation ---
def test_validate_accepts_full_object():
    raw = {k: f"section {k}" for k in SECTION_KEYS}
    assert validate_sections(raw) == raw


def test_validate_rejects_missing_section():
    raw = dict.fromkeys(SECTION_KEYS[:-1], "x")
    with pytest.raises(ValueError, match="missing or empty"):
        validate_sections(raw)


def test_validate_rejects_empty_and_non_string():
    with pytest.raises(ValueError):
        validate_sections({**dict.fromkeys(SECTION_KEYS, "x"), "executive_summary": "  "})
    with pytest.raises(ValueError):
        validate_sections({**dict.fromkeys(SECTION_KEYS, "x"), "risk_analysis": 5})
    with pytest.raises(ValueError):
        validate_sections("not an object")


# --- Offline fallback ---
def test_offline_sections_complete_and_carry_verdict():
    sections = build_offline_sections("Road work", _decision())
    assert set(sections) == set(SECTION_KEYS)
    assert all(v.strip() for v in sections.values())
    assert "REVIEW" in sections["executive_summary"]
    assert "62.5" in sections["executive_summary"]
    assert "PERFORMANCE_GUARANTEE" in sections["risk_analysis"]
