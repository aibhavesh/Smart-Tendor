"""Phase 7 AI-Analyst service and API tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from tender_intel.application.dto.analyst import SECTION_KEYS
from tender_intel.application.dto.decision import DecisionResult
from tender_intel.application.services.analyst_service import AnalystService
from tender_intel.domain.decision.models import (
    QualificationResult,
    QualificationRuleResult,
    Recommendation,
    RiskAssessment,
    RiskCategoryResult,
)
from tender_intel.domain.entities import Tender
from tender_intel.domain.enums.recommendation import RecommendationVerdict
from tender_intel.domain.enums.risk import RiskCategory, RiskLevel
from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.infrastructure.llm.gemini import AIProviderError
from tests.integration.helpers import auth_headers


def _decision(verdict=RecommendationVerdict.GO) -> DecisionResult:
    qual = QualificationResult(True, [QualificationRuleResult("work_value", True, "ok")])
    risk = RiskAssessment(
        [RiskCategoryResult(RiskCategory.HIGH_EMD, RiskLevel.LOW, Decimal("2.0"), ["e"])],
        RiskLevel.LOW,
        Decimal("2.0"),
        RiskCategory.HIGH_EMD,
    )
    rec = Recommendation(
        verdict,
        Decimal("75.0"),
        Decimal("0.9"),
        ["pro"],
        ["con"],
        ["doc"],
        ["rule_4c_qualified_go"],
    )
    return DecisionResult(qualification=qual, risk=risk, recommendation=rec)


class _FakeDecision:
    def __init__(self, result=None, error=None):
        self._result = result or _decision()
        self._error = error

    async def compute(self, tender_id):
        if self._error:
            raise self._error
        return self._result


class _FakeTenders:
    def __init__(self, tender):
        self._tender = tender

    async def get(self, tender_id):
        return self._tender


class _GoodLLM:
    async def generate_json(self, *, system, prompt, schema):
        return {k: f"LLM narrative for {k}" for k in SECTION_KEYS}


class _FailingLLM:
    async def generate_json(self, *, system, prompt, schema):
        raise AIProviderError("provider down")


class _MalformedLLM:
    async def generate_json(self, *, system, prompt, schema):
        return {"executive_summary": "only one section"}  # missing the rest


def _service(llm, *, decision=None, tender=None) -> AnalystService:
    return AnalystService(
        decision=_FakeDecision(result=decision),
        tenders=_FakeTenders(tender or Tender(tender_number="T-1", title="Road")),
        llm=llm,
    )


async def test_uses_llm_when_output_valid():
    report = await _service(_GoodLLM()).generate_report(uuid4())
    assert report.generated_by == "gemini"
    assert report.sections["executive_summary"].startswith("LLM narrative")
    # Verdict / win carried verbatim from the decision, not the LLM.
    assert report.verdict is RecommendationVerdict.GO
    assert report.win_probability == Decimal("75.0")


async def test_falls_back_when_provider_fails():
    report = await _service(_FailingLLM()).generate_report(uuid4())
    assert report.generated_by == "offline"
    assert set(report.sections) == set(SECTION_KEYS)
    assert report.verdict is RecommendationVerdict.GO  # still verbatim
    assert report.win_probability == Decimal("75.0")


async def test_falls_back_when_output_malformed():
    report = await _service(_MalformedLLM()).generate_report(uuid4())
    assert report.generated_by == "offline"
    assert all(report.sections.values())


async def test_verdict_is_never_taken_from_llm():
    # Even a NO_BID decision keeps its verdict regardless of narrative prose.
    report = await _service(
        _GoodLLM(), decision=_decision(RecommendationVerdict.NO_BID)
    ).generate_report(uuid4())
    assert report.verdict is RecommendationVerdict.NO_BID


async def test_report_requires_computed_decision():
    service = AnalystService(
        decision=_FakeDecision(error=DomainValidationError("not parsed")),
        tenders=_FakeTenders(Tender(tender_number="T-1", title="X")),
        llm=_GoodLLM(),
    )
    with pytest.raises(DomainValidationError):
        await service.generate_report(uuid4())


# --- API (no Gemini key configured in tests -> deterministic offline path) ---
async def test_report_endpoint_uses_offline_fallback(client, app_db):
    headers = await auth_headers(client, app_db)
    tender = (
        await client.post(
            "/tenders", json={"tender_number": "T-R", "title": "Road"}, headers=headers
        )
    ).json()
    await client.post(
        f"/tenders/{tender['id']}/documents/upload",
        files={
            "file": ("t.txt", b"Name of Work: Road\nEstimated Cost: Rs. 50 lakh\n", "text/plain")
        },
        headers=headers,
    )
    await client.post(f"/tenders/{tender['id']}/extract", headers=headers)

    analyzed = await client.post(f"/tenders/{tender['id']}/analyze", headers=headers)
    report = await client.get(f"/tenders/{tender['id']}/report", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["generated_by"] == "offline"  # no API key in tests
    assert set(body["sections"]) == set(SECTION_KEYS)
    # The report's verdict matches the deterministic analysis.
    assert body["verdict"] == analyzed.json()["recommendation"]["verdict"]


async def test_report_requires_parsed_tender(client, app_db):
    headers = await auth_headers(client, app_db)
    tender = (
        await client.post("/tenders", json={"tender_number": "T-U", "title": "X"}, headers=headers)
    ).json()
    # REGISTERED (never extracted) -> decision cannot be computed -> 422.
    resp = await client.get(f"/tenders/{tender['id']}/report", headers=headers)
    assert resp.status_code == 422
