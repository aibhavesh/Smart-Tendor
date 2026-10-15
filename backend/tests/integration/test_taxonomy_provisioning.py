"""Automatic work-type taxonomy provisioning.

A database created from migrations alone has the ``work_types`` tables and none of
their rows. These tests pin the behaviour that closes that gap: the taxonomy is
provisioned on the first past-project write, once, and only when it is actually
empty.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy import func, select

from tender_intel.application.dto.past_project import PastProjectCreate
from tender_intel.application.services.past_project_service import PastProjectService
from tender_intel.application.services.work_type_seed_service import WorkTypeSeedService
from tender_intel.application.services.work_type_service import WorkTypeService
from tender_intel.domain.entities.work_type import WorkType, WorkTypeAlias
from tender_intel.domain.enums.work_type import AliasKind
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.db.orm import WorkTypeAliasModel, WorkTypeModel
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.eligibility_repo import (
    SqlAlchemyPortfolioVersionRepository,
)
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.work_type_repo import SqlAlchemyWorkTypeRepository
from tender_intel.infrastructure.seed.work_type_seed import load_packaged_seed


async def _counts(session) -> tuple[int, int]:
    types = (await session.execute(select(func.count()).select_from(WorkTypeModel))).scalar_one()
    aliases = (
        await session.execute(select(func.count()).select_from(WorkTypeAliasModel))
    ).scalar_one()
    return types, aliases


def _seed_service(session) -> WorkTypeSeedService:
    return WorkTypeSeedService(
        work_types=SqlAlchemyWorkTypeRepository(session),
        projects=SqlAlchemyPastProjectRepository(session),
        versions=SqlAlchemyPortfolioVersionRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
    )


def _work_type_service(session) -> WorkTypeService:
    return WorkTypeService(
        work_types=SqlAlchemyWorkTypeRepository(session),
        projects=SqlAlchemyPastProjectRepository(session),
        versions=SqlAlchemyPortfolioVersionRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
    )


def _project_service(session, seed: WorkTypeSeedService | None, fakes) -> PastProjectService:
    return PastProjectService(
        projects=SqlAlchemyPastProjectRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
        embeddings=fakes.embeddings,
        vectors=fakes.vectors,
        collection="test",
        seed=seed,
    )


async def test_ensure_taxonomy_provisions_the_packaged_seed(session):
    """The empty case is the whole point: it must fill in what migrations left out."""
    assert await _counts(session) == (0, 0)

    outcome = await _seed_service(session).ensure_taxonomy()

    assert outcome is not None
    assert outcome.work_types_created > 0
    assert outcome.aliases_created > 0
    types, aliases = await _counts(session)
    assert types == outcome.work_types_created
    assert aliases == outcome.aliases_created


async def test_ensure_taxonomy_matches_the_packaged_seed_exactly(session):
    """The provisioned taxonomy is the shipped file, not an approximation of it."""
    seed = load_packaged_seed()

    await _seed_service(session).ensure_taxonomy()

    stored = {code for (code,) in (await session.execute(select(WorkTypeModel.code))).all()}
    assert stored == {entry.code for entry in seed.work_types}


async def test_ensure_taxonomy_is_a_no_op_when_already_populated(session):
    await _seed_service(session).ensure_taxonomy()
    before = await _counts(session)

    assert await _seed_service(session).ensure_taxonomy() is None

    assert await _counts(session) == before


async def test_ensure_taxonomy_is_repeatable(session):
    """Idempotent under repetition: a second provisioner adds nothing."""
    first = await _seed_service(session).ensure_taxonomy()
    second = await _seed_service(session).ensure_taxonomy()

    assert first is not None
    assert second is None
    types, aliases = await _counts(session)
    assert types == first.work_types_created
    assert aliases == first.aliases_created


async def test_ensure_taxonomy_writes_one_audit_entry_with_no_actor(session):
    """A system act, recorded as one entry with a null actor.

    Null because the user who triggered it did not create 40 work types, and
    naming them would put a false entry in the trail.
    """
    await _seed_service(session).ensure_taxonomy()

    entries = await SqlAlchemyAuditLogRepository(session).list(PageRequest(limit=50))
    seed_entries = [a for a in entries.items if a.action == "work_type.seed_load"]

    assert len(seed_entries) == 1
    assert seed_entries[0].actor_id is None
    assert seed_entries[0].entity_type == "WorkType"
    diff = seed_entries[0].diff or {}
    assert diff["types_only"] is True
    assert diff["work_types_created"] > 0


async def test_load_keeps_an_existing_operator_alias(session):
    """Global alias uniqueness means a collision must drop the seed's copy.

    An operator who created an alias by hand through the admin API owns that
    phrase. Overwriting it with the seed's alias would silently retarget it.

    Reached through ``load`` rather than ``ensure_taxonomy`` on purpose: an alias
    cannot exist without its work type, so any pre-existing alias means the
    taxonomy is *not* empty and the provisioner correctly declines to run. This
    collision is the explicit loader's problem, and the concurrent-winner case
    below covers the provisioner.
    """
    repo = SqlAlchemyWorkTypeRepository(session)
    seed = load_packaged_seed()
    first = seed.work_types[0]
    contested = first.aliases[0]

    existing = await repo.add(
        WorkType(code="OPERATOR_OWN", name="Operator's own", category=first.category)
    )
    await repo.add_alias(
        WorkTypeAlias(work_type_id=existing.id, alias=contested.alias, kind=contested.kind)
    )

    await _seed_service(session).load(load_packaged_seed(), types_only=True)

    owner = (
        (
            await session.execute(
                select(WorkTypeAliasModel.work_type_id).where(
                    WorkTypeAliasModel.alias_normalised == contested.normalised
                )
            )
        )
        .scalars()
        .first()
    )
    assert owner == existing.id
    # Every seeded type landed; only the duplicate alias was dropped.
    assert await repo.get_by_code(first.code) is not None


async def test_ensure_taxonomy_survives_a_concurrent_winner(session):
    """A lost race is success, not an error, and destroys nothing already written.

    Two application instances can both observe an empty taxonomy. The loser must
    not raise, and its failed insert must roll back only to its own savepoint so
    the rows written before it survive.
    """
    repo = SqlAlchemyWorkTypeRepository(session)
    await _seed_service(session).ensure_taxonomy()
    before = await _counts(session)

    category = load_packaged_seed().work_types[0].category
    winner = await repo.add(WorkType(code="RACE_CODE", name="Winner", category=category))
    assert winner is not None
    midpoint = await _counts(session)

    # The loser tries the same unique code, and also an alias already in use.
    loser = await repo.add_ignoring_conflict(
        WorkType(code="RACE_CODE", name="Loser", category=category)
    )
    assert loser is None

    taken = (await session.execute(select(WorkTypeAliasModel).limit(1))).scalars().first()
    assert taken is not None
    assert (
        await repo.add_alias_ignoring_conflict(
            WorkTypeAlias(
                work_type_id=winner.id,
                alias=taken.alias,
                kind=AliasKind(taken.alias_kind),
            )
        )
        is None
    )

    # The winner's row and every seed row are still present.
    assert await _counts(session) == midpoint
    assert midpoint[0] == before[0] + 1
    assert await repo.get_by_code("RACE_CODE") is not None
    assert len(await repo.list_active()) == midpoint[0]


@pytest_asyncio.fixture
async def fakes():
    """Offline embeddings and an in-memory vector store, as conftest does."""
    from qdrant_client import AsyncQdrantClient

    from tender_intel.infrastructure.embeddings.hash_embedding import HashEmbeddingProvider
    from tender_intel.infrastructure.vector.qdrant_store import QdrantVectorStore

    qdrant = AsyncQdrantClient(location=":memory:")
    try:
        yield SimpleNamespace(
            embeddings=HashEmbeddingProvider(dimension=384),
            vectors=QdrantVectorStore(qdrant),
        )
    finally:
        await qdrant.close()


async def test_past_project_create_provisions_the_taxonomy(session, fakes):
    """The hook that closes the original gap, on the single-create path."""
    service = _project_service(session, _seed_service(session), fakes)

    project = await service.create(PastProjectCreate(name="OFC cable laying"))

    assert project.name == "OFC cable laying"
    types, aliases = await _counts(session)
    assert types > 0
    assert aliases > 0


async def test_past_project_create_without_the_hook_still_works(session, fakes):
    """The hook is optional, so callers that omit it are unaffected."""
    service = _project_service(session, None, fakes)

    project = await service.create(PastProjectCreate(name="Anything"))

    assert project.name == "Anything"
    assert await _counts(session) == (0, 0)
