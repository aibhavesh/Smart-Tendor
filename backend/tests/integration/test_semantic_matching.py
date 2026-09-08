"""Phase 5 semantic matching: indexing, retrieval, eligibility and ranking."""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from qdrant_client import AsyncQdrantClient

from tender_intel.application.dto.past_project import PastProjectCreate
from tender_intel.application.services.matching_service import MatchingService
from tender_intel.application.services.past_project_service import PastProjectService
from tender_intel.domain.entities import PastProject, Tender, TenderMetadata
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.embeddings.hash_embedding import HashEmbeddingProvider
from tender_intel.infrastructure.extraction.rule_metadata import RuleBasedMetadataExtractor
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyTenderMetadataRepository,
    SqlAlchemyTenderRepository,
)
from tender_intel.infrastructure.vector.qdrant_store import QdrantVectorStore

COLLECTION = "test_projects"


class _PlainText:
    def extract_text(self, content: bytes) -> str:
        return content.decode("utf-8")


@pytest_asyncio.fixture
async def vectors() -> AsyncIterator[QdrantVectorStore]:
    client = AsyncQdrantClient(location=":memory:")
    yield QdrantVectorStore(client)
    await client.close()


def _project_service(session, vectors) -> PastProjectService:
    return PastProjectService(
        projects=SqlAlchemyPastProjectRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
        embeddings=HashEmbeddingProvider(),
        vectors=vectors,
        collection=COLLECTION,
        text_extractor=_PlainText(),
        metadata_backend=RuleBasedMetadataExtractor(),
    )


def _matching_service(session, vectors) -> MatchingService:
    return MatchingService(
        tenders=SqlAlchemyTenderRepository(session),
        metadata_repo=SqlAlchemyTenderMetadataRepository(session),
        projects=SqlAlchemyPastProjectRepository(session),
        embeddings=HashEmbeddingProvider(),
        vectors=vectors,
        collection=COLLECTION,
    )


async def test_create_indexes_and_delete_removes(session, vectors):
    service = _project_service(session, vectors)
    project = await service.create(
        PastProjectCreate(name="Road construction highway", work_value=Decimal("20000000"))
    )
    assert project.embedding_indexed is True

    # The vector is retrievable.
    query_vec = (await HashEmbeddingProvider().embed(["road construction"]))[0]
    matches = await vectors.search(COLLECTION, query_vec, 5)
    assert any(m.id == project.id for m in matches)

    await service.delete(project.id)
    matches_after = await vectors.search(COLLECTION, query_vec, 5)
    assert all(m.id != project.id for m in matches_after)


async def test_backfill_indexes_unindexed(session, vectors):
    # Insert directly (bypassing the service) so it starts unindexed.
    repo = SqlAlchemyPastProjectRepository(session)
    project = await repo.add(PastProject(name="Metro rail", work_value=Decimal("30000000")))
    assert project.embedding_indexed is False

    service = _project_service(session, vectors)
    count = await service.backfill()
    assert count == 1

    refreshed = await repo.get(project.id)
    assert refreshed.embedding_indexed is True
    assert (await repo.list_unindexed(10)) == []


async def test_matching_ranks_eligible_first_then_similarity(session, vectors):
    projects = _project_service(session, vectors)
    p1 = await projects.create(
        PastProjectCreate(name="Road construction highway", work_value=Decimal("20000000"))
    )  # eligible + most similar
    p2 = await projects.create(
        PastProjectCreate(name="Road widening project", work_value=Decimal("5000000"))
    )  # below threshold -> ineligible
    p3 = await projects.create(
        PastProjectCreate(name="Bridge painting work", work_value=Decimal("30000000"))
    )  # eligible but dissimilar

    tenders = SqlAlchemyTenderRepository(session)
    tender = await tenders.add(Tender(tender_number="T-M", title="Road construction"))
    await SqlAlchemyTenderMetadataRepository(session).upsert(
        TenderMetadata(
            tender_id=tender.id,
            work_name=ExtractedField.known("Road construction", 0.8),
            eligibility_criteria=ExtractedField.known(
                "Bidder must have completed similar work of value not less than Rs. 1 crore", 0.7
            ),
        )
    )

    result = await _matching_service(session, vectors).match(tender.id, top_k=10)

    assert result.min_required_value == Decimal("10000000")
    ids = [c.project_id for c in result.candidates]
    # Eligible ones (p1, p3) rank before the ineligible p2; p1 is most similar.
    assert ids.index(p1.id) < ids.index(p2.id)
    assert ids.index(p3.id) < ids.index(p2.id)
    assert ids[0] == p1.id

    by_id = {c.project_id: c for c in result.candidates}
    assert by_id[p1.id].eligible is True
    assert by_id[p2.id].eligible is False
    assert "below the required" in by_id[p2.id].reasons[0]


async def test_matching_without_metadata_uses_similarity_only(session, vectors):
    projects = _project_service(session, vectors)
    await projects.create(PastProjectCreate(name="Water pipeline laying"))

    tenders = SqlAlchemyTenderRepository(session)
    tender = await tenders.add(Tender(tender_number="T-N", title="Water pipeline"))

    result = await _matching_service(session, vectors).match(tender.id)
    assert result.min_required_value is None
    assert all(c.eligible for c in result.candidates)  # no constraint -> all eligible


async def test_list_pagination(session, vectors):
    service = _project_service(session, vectors)
    for i in range(3):
        await service.create(PastProjectCreate(name=f"Project {i}"))
    page = await service.list(PageRequest(limit=2))
    assert page.total == 3
    assert len(page.items) == 2
