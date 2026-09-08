"""Prompt construction, response validation and the deterministic offline
fallback for the AI Analyst (FR-330..FR-335).

The LLM only writes prose. The verdict, win probability and confidence come from
the deterministic engine and are never taken from the model output.
"""

from __future__ import annotations

import json
from typing import Any

from tender_intel.application.dto.analyst import SECTION_KEYS
from tender_intel.application.dto.decision import DecisionResult

_SYSTEM = (
    "You are a professional tender bid analyst for a construction and IT-services "
    "company in India. Write a clear, factual bid-analysis report. You are given a "
    "FIXED recommendation, win probability and confidence computed by a deterministic "
    "rules engine — you must NOT change, contradict or re-derive them; explain and "
    "narrate them for a bid manager. Be concise and specific. Return ONLY a JSON "
    "object matching the provided schema, with a non-empty string for every section."
)

# JSON schema the model must satisfy (OpenAPI subset accepted by Gemini).
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {key: {"type": "string"} for key in SECTION_KEYS},
    "required": list(SECTION_KEYS),
}


def _facts(title: str, decision: DecisionResult) -> dict[str, Any]:
    rec = decision.recommendation
    qual = decision.qualification
    risk = decision.risk
    return {
        "tender_title": title,
        "recommendation": {
            "verdict": rec.verdict.value,
            "win_probability_pct": str(rec.win_probability),
            "confidence": str(rec.confidence),
            "applied_rules": rec.applied_rules,
        },
        "qualification": {
            "qualified": qual.qualified,
            "rules": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in qual.rules],
        },
        "risk": {
            "overall_severity": risk.overall_severity.value,
            "overall_score_out_of_10": str(risk.overall_score),
            "categories": [
                {"category": c.category.value, "severity": c.severity.value, "evidence": c.evidence}
                for c in risk.categories
            ],
        },
        "pros": rec.pros,
        "cons": rec.cons,
        "document_checklist": rec.document_checklist,
    }


def build_prompt(title: str, decision: DecisionResult) -> tuple[str, str, dict[str, Any]]:
    facts = json.dumps(_facts(title, decision), indent=2)
    prompt = (
        "Produce the five report sections from these engine-computed facts. Keep the "
        "verdict, win probability and confidence exactly as given.\n\n"
        f"FACTS:\n{facts}\n\n"
        f"Sections required (JSON keys): {', '.join(SECTION_KEYS)}."
    )
    return _SYSTEM, prompt, RESPONSE_SCHEMA


def validate_sections(raw: object) -> dict[str, str]:
    """Return the five sections, or raise ValueError on malformed output."""
    if not isinstance(raw, dict):
        raise ValueError("LLM output is not a JSON object")
    sections: dict[str, str] = {}
    for key in SECTION_KEYS:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"missing or empty section: {key}")
        sections[key] = value.strip()
    return sections


# --------------------------------------------------------------------------- #
# Deterministic offline fallback — no LLM, never fails (NFR-405).
# --------------------------------------------------------------------------- #
def build_offline_sections(title: str, decision: DecisionResult) -> dict[str, str]:
    rec = decision.recommendation
    qual = decision.qualification
    risk = decision.risk

    executive = (
        f"For '{title}', the decision engine recommends {rec.verdict.value} with an "
        f"estimated win probability of {rec.win_probability}% and a confidence of "
        f"{rec.confidence}. This verdict follows the applied rule(s): "
        f"{', '.join(rec.applied_rules)}."
    )

    qualification = (
        "Qualification: "
        + ("the bidder is QUALIFIED. " if qual.qualified else "the bidder is NOT QUALIFIED. ")
        + " ".join(f"{r.name} — {'PASS' if r.passed else 'FAIL'}: {r.detail}" for r in qual.rules)
    )

    elevated = [
        f"{c.category.value} ({c.severity.value})"
        for c in risk.categories
        if c.severity.value in ("MEDIUM", "HIGH")
    ]
    risk_text = (
        f"Overall risk is {risk.overall_severity.value} "
        f"(score {risk.overall_score} out of 10). "
        + (
            "Elevated categories: " + "; ".join(elevated) + "."
            if elevated
            else "No category is elevated above LOW."
        )
    )

    outlook = (
        f"The win probability is {rec.win_probability}%. "
        + ("Key strengths: " + "; ".join(rec.pros[:3]) + ". " if rec.pros else "")
        + ("Watch-outs: " + "; ".join(rec.cons[:3]) + "." if rec.cons else "")
    )

    actions = (
        "Prepare and submit: "
        + "; ".join(rec.document_checklist)
        + "."
        + (" Address before bidding: " + "; ".join(rec.cons[:3]) + "." if rec.cons else "")
    )

    return {
        "executive_summary": executive,
        "qualification_analysis": qualification,
        "risk_analysis": risk_text,
        "win_probability_outlook": outlook,
        "recommended_actions": actions,
    }
