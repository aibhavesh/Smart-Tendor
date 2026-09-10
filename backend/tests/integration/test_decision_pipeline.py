"""Phase 6 decision orchestration: service end-to-end and API surface (PRD §13)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from qdrant_client import AsyncQdrantClient

from tender_intel.application.dto.past_project import PastProjectCreate
from tender_intel.application.services.decision_service import DecisionService
from tender_intel.application.services.eligibility_service import EligibilityService
from tender_intel.application.services.matching_service import MatchingService
from tender_intel.application.services.past_project_service import PastProjectService
from tender_intel.core.config import Environment, Settings
from tender_intel.domain.entities import Tender, TenderMetadata
from tender_intel.domain.entities.company_turnover import CompanyTurnover
from tender_intel.domain.entities.work_type import (
    PastProjectWorkType,
    WorkType,
    WorkTypeAlias,
)
from tender_intel.domain.enums.eligibility import EligibilityStatus
from tender_intel.domain.enums.recommendation import RecommendationVerdict
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.enums.work_type import (
    AliasKind,
    WorkTypeCategory,
    WorkTypeLinkSource,
)
from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.domain.services.financial_year import completed_years_before
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.infrastructure.embeddings.hash_embedding import HashEmbeddingProvider
from tender_intel.infrastructure.extraction.rule_metadata import RuleBasedMetadataExtractor
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.eligibility_repo import (
    SqlAlchemyCompanyTurnoverRepository,
    SqlAlchemyPortfolioVersionRepository,
    SqlAlchemyTenderEligibilityRepository,
)
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyTenderMetadataRepository,
    SqlAlchemyTenderRepository,
)
from tender_intel.infrastructure.repositories.work_type_repo import (
    SqlAlchemyWorkTypeRepository,
)
from tender_intel.infrastructure.vector.qdrant_store import QdrantVectorStore
from tests.integration.helpers import auth_headers

EV = Decimal("5000000")  # 50 lakh
COLLECTION = "test_decision"


class _PlainText:
    def extract_text(self, content: bytes) -> str:  # pragma: no cover - unused
        return content.decode("utf-8")


CLOSING = date(2026, 12, 1)  # FY 2026-27; window closes at 2025-26
CERT = date(2024, 6, 1)  # inside the seven completed years before CLOSING


def _settings() -> Settings:
    return Settings(
        environment=Environment.CI,
        jwt_secret="test-secret-value-that-is-long-enough-1234",
    )


async def _seed_taxonomy(session) -> WorkType:
    """One work type whose alias matches the seeded tender scope exactly."""
    repo = SqlAlchemyWorkTypeRepository(session)
    work_type = await repo.add(
        WorkType(
            code="RCC_ROAD", name="RCC road works", category=WorkTypeCategory.TELECOM_NETWORKING
        )
    )
    await repo.add_alias(
        WorkTypeAlias(work_type_id=work_type.id, alias="rcc road", kind=AliasKind.SYNONYM)
    )
    return work_type


async def _seed_turnover(session, amount: str = "10000000") -> None:
    """The three completed financial years the screen averages over."""
    repo = SqlAlchemyCompanyTurnoverRepository(session)
    for year in completed_years_before(CLOSING, 3):
        await repo.add(
            CompanyTurnover(financial_year=year.label, contractual_turnover=Decimal(amount))
        )


def _eligibility(session, vectors) -> EligibilityService:
    return EligibilityService(
        tenders=SqlAlchemyTenderRepository(session),
        metadata_repo=SqlAlchemyTenderMetadataRepository(session),
        projects=SqlAlchemyPastProjectRepository(session),
        work_types=SqlAlchemyWorkTypeRepository(session),
        turnover=SqlAlchemyCompanyTurnoverRepository(session),
        results=SqlAlchemyTenderEligibilityRepository(session),
        versions=SqlAlchemyPortfolioVersionRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
        embeddings=HashEmbeddingProvider(),
        vectors=vectors,
        collection=COLLECTION,
    )


@pytest_asyncio.fixture
async def qdrant() -> AsyncIterator[QdrantVectorStore]:
    client = AsyncQdrantClient(location=":memory:")
    yield QdrantVectorStore(client)
    await client.close()


def _matching(session, vectors) -> MatchingService:
    return MatchingService(
        tenders=SqlAlchemyTenderRepository(session),
        metadata_repo=SqlAlchemyTenderMetadataRepository(session),
        projects=SqlAlchemyPastProjectRepository(session),
        embeddings=HashEmbeddingProvider(),
        vectors=vectors,
        collection=COLLECTION,
    )


def _decision(session, vectors, settings=None) -> DecisionService:
    return DecisionService(
        tenders=SqlAlchemyTenderRepository(session),
        metadata_repo=SqlAlchemyTenderMetadataRepository(session),
        matching=_matching(session, vectors),
        eligibility=_eligibility(session, vectors),
        audits=SqlAlchemyAuditLogRepository(session),
    )


async def _index_project(
    session, vectors, name: str, value: Decimal, *, work_type: WorkType | None = None
) -> None:
    service = PastProjectService(
        projects=SqlAlchemyPastProjectRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
        embeddings=HashEmbeddingProvider(),
        vectors=vectors,
        collection=COLLECTION,
        text_extractor=_PlainText(),
        metadata_backend=RuleBasedMetadataExtractor(),
    )
    project = await service.create(
        PastProjectCreate(name=name, work_value=value, completion_certificate_date=CERT)
    )
    if work_type is not None:
        await SqlAlchemyWorkTypeRepository(session).add_tag(
            PastProjectWorkType(
                project_id=project.id,
                work_type_id=work_type.id,
                source=WorkTypeLinkSource.SEED,
            )
        )


async def _seed_parsed(session, *, eligibility: bool) -> Tender:
    repo = SqlAlchemyTenderRepository(session)
    tender = await repo.add(Tender(tender_number="T-DEC", title="RCC Road"))
    tender.transition_to(TenderStatus.DOWNLOADED)
    tender.transition_to(TenderStatus.PARSED)
    await repo.update(tender)

    known = ExtractedField.known
    fields = {
        "work_name": known("RCC Road", 0.9),
        "estimated_value": known(EV, 0.9),
        "emd_amount": known(Decimal("50000"), 0.9),  # 1% -> HIGH_EMD LOW
        "tender_fee": known(Decimal("5000"), 0.9),
        "closing_date": known(CLOSING, 0.9),
        "completion_period": known("12 months", 0.9),  # 360 days -> no timeline risk
        "location": known("Indore", 0.9),
        "department": known("PWD", 0.9),
        "scope_of_work": known("Construction of RCC road", 0.7),
    }
    if eligibility:
        fields["eligibility_criteria"] = known("Similar works of value not less than 40 lakh", 0.7)
    await SqlAlchemyTenderMetadataRepository(session).upsert(
        TenderMetadata(tender_id=tender.id, **fields)
    )
    return tender


async def test_eligible_with_no_eligibility_rules_is_go(session, qdrant):
    work_type = await _seed_taxonomy(session)
    await _seed_turnover(session)
    await _index_project(session, qdrant, "Similar road project", EV, work_type=work_type)
    tender = await _seed_parsed(session, eligibility=False)  # -> rule 4c GO

    result = await _decision(session, qdrant).analyze(tender.id)

    assert result.qualification.status is EligibilityStatus.ELIGIBLE
    assert result.qualification.qualified is True
    assert result.recommendation.verdict is RecommendationVerdict.GO
    assert result.recommendation.win_probability > 0
    assert Decimal("0") <= result.recommendation.confidence <= Decimal("1")
    assert len(result.risk.categories) == 6

    refreshed = await SqlAlchemyTenderRepository(session).get(tender.id)
    assert refreshed.status is TenderStatus.ANALYZED


async def test_missing_turnover_is_review_not_no_bid(session, qdrant):
    """No certified turnover recorded is an unknown, not a refusal.

    Rule 1b routes it to a person. Grouping it with NOT_ELIGIBLE instead would
    return NO_BID for every tender until an administrator enters three years.
    """
    work_type = await _seed_taxonomy(session)
    await _index_project(session, qdrant, "Similar road project", EV, work_type=work_type)
    tender = await _seed_parsed(session, eligibility=False)

    result = await _decision(session, qdrant).analyze(tender.id)

    assert result.qualification.status is EligibilityStatus.INDETERMINATE
    assert result.recommendation.verdict is RecommendationVerdict.REVIEW
    assert "rule_1b_indeterminate" in result.recommendation.applied_rules
    # FR-326: the uncertainty is visible, not folded into a number.
    assert any("completed financial years" in c for c in result.recommendation.cons)


async def test_turnover_below_the_requirement_is_no_bid(session, qdrant):
    work_type = await _seed_taxonomy(session)
    await _seed_turnover(session, amount="1")
    await _index_project(session, qdrant, "Similar road project", EV, work_type=work_type)
    tender = await _seed_parsed(session, eligibility=False)

    result = await _decision(session, qdrant).analyze(tender.id)

    assert result.qualification.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.recommendation.verdict is RecommendationVerdict.NO_BID
    assert result.recommendation.win_probability == Decimal("0")  # FR-322


async def test_analyze_requires_parsed(session, qdrant):
    repo = SqlAlchemyTenderRepository(session)
    tender = await repo.add(Tender(tender_number="T-RAW", title="X"))  # REGISTERED
    with pytest.raises(DomainValidationError):
        await _decision(session, qdrant).compute(tender.id)


async def test_recompute_is_deterministic(session, qdrant):
    work_type = await _seed_taxonomy(session)
    await _seed_turnover(session)
    await _index_project(session, qdrant, "Similar road project", EV, work_type=work_type)
    tender = await _seed_parsed(session, eligibility=True)
    service = _decision(session, qdrant)
    a = await service.compute(tender.id)
    b = await service.compute(tender.id)
    assert a.recommendation.verdict is b.recommendation.verdict
    assert a.recommendation.win_probability == b.recommendation.win_probability
    assert a.risk.overall_score == b.risk.overall_score


# --- API ---
async def test_analyze_endpoint_flow(client, app_db):
    headers = await auth_headers(client, app_db)
    tender = (
        await client.post(
            "/tenders", json={"tender_number": "T-A", "title": "Road"}, headers=headers
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
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["recommendation"]["verdict"] in ("GO", "REVIEW", "NO_BID")
    assert isinstance(body["recommendation"]["win_probability"], (int, float))
    assert len(body["risk"]["categories"]) == 6
    assert len(body["qualification"]["rules"]) == 3

    tender_after = await client.get(f"/tenders/{tender['id']}", headers=headers)
    assert tender_after.json()["status"] == "ANALYZED"

    rec = await client.get(f"/tenders/{tender['id']}/recommendation", headers=headers)
    assert rec.status_code == 200
