"""Loading the work-type seed into the database (feature spec §6).

Exercises the loader against a synthetic seed shaped like the real one, so the
behaviour is pinned before the real file and the portfolio arrive.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender_intel.application.services.work_type_seed_service import WorkTypeSeedService
from tender_intel.domain.entities import PastProject
from tender_intel.domain.enums.work_type import WorkTypeLinkSource
from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.eligibility_repo import (
    SqlAlchemyPortfolioVersionRepository,
)
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.work_type_repo import SqlAlchemyWorkTypeRepository
from tender_intel.infrastructure.seed.work_type_seed import parse_seed


def seed_payload(*, projects=("TELE 22",), second_projects=("NTPC Vindhyachal",)) -> dict:
    return {
        "version": "1.0",
        "source": "7_YEAR_PROJECT_DETAILS.xlsx",
        "work_types": [
            {
                "code": "OFC_CABLE_SUPPLY",
                "name": "Optical fibre cable supply",
                "category": "TELECOM_NETWORKING",
                "description": "Supply and installation of optical fibre cable.",
                "aliases": [
                    {"alias": "OFC", "kind": "ABBREVIATION"},
                    {"alias": "optical fibre cable", "kind": "EXPANSION"},
                ],
                "projects": list(projects),
            },
            {
                "code": "LAN_REVAMP",
                "name": "Local area network revamping",
                "category": "TELECOM_NETWORKING",
                "description": "Provision and revamping of structured LAN.",
                "aliases": [{"alias": "LAN", "kind": "ABBREVIATION"}],
                "projects": list(second_projects),
            },
        ],
    }


def service(session) -> WorkTypeSeedService:
    return WorkTypeSeedService(
        work_types=SqlAlchemyWorkTypeRepository(session),
        projects=SqlAlchemyPastProjectRepository(session),
        versions=SqlAlchemyPortfolioVersionRepository(session),
        audits=SqlAlchemyAuditLogRepository(session),
    )


async def seed_project(session, name: str, loa: str) -> PastProject:
    return await SqlAlchemyPastProjectRepository(session).add(
        PastProject(name=name, work_value=Decimal("1000000"), loa_reference=loa)
    )


async def seed_portfolio(session) -> None:
    await seed_project(session, "OFC route, Ahmedabad", "TELE 22")
    await seed_project(session, "NTPC LAN revamp", "NTPC Vindhyachal")


# --------------------------------------------------------------------------- #
# Planning — writes nothing
# --------------------------------------------------------------------------- #
async def test_plan_reports_what_would_happen_without_writing(session):
    await seed_portfolio(session)
    plan = await service(session).plan(parse_seed(seed_payload()))

    assert plan.work_types_created == 2
    assert plan.aliases_created == 3
    assert plan.tags_to_create == 2
    assert plan.can_load_tags

    # Nothing was written.
    listed = await SqlAlchemyWorkTypeRepository(session).list(PageRequest(limit=50))
    assert listed.total == 0


async def test_plan_names_the_project_each_reference_resolves_to(session):
    await seed_portfolio(session)
    plan = await service(session).plan(parse_seed(seed_payload()))
    # This pairing is the only place a mis-attribution is visible to a human.
    assert plan.resolved["TELE 22"] == "OFC route, Ahmedabad"
    assert "OFC route, Ahmedabad" in plan.describe()


async def test_plan_reports_unmatched_references(session):
    await seed_project(session, "OFC route", "TELE 22")  # NTPC missing
    plan = await service(session).plan(parse_seed(seed_payload()))
    assert plan.unmatched == ["NTPC Vindhyachal"]
    assert not plan.can_load_tags
    assert "BLOCKED" in plan.describe()


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
async def test_a_full_load_creates_types_aliases_and_tags(session):
    await seed_portfolio(session)
    outcome = await service(session).load(parse_seed(seed_payload()))

    assert outcome.work_types_created == 2
    assert outcome.aliases_created == 3
    assert outcome.tags_created == 2

    repo = SqlAlchemyWorkTypeRepository(session)
    assert len(await repo.list_active()) == 2
    tags = await repo.list_tags()
    assert {t.source for t in tags} == {WorkTypeLinkSource.SEED}
    assert all(t.evidence and "workbook reference" in t.evidence for t in tags)


async def test_the_load_is_idempotent(session):
    await seed_portfolio(session)
    payload = parse_seed(seed_payload())
    await service(session).load(payload)
    second = await service(session).load(payload)

    assert second.work_types_created == 0
    assert second.aliases_created == 0
    repo = SqlAlchemyWorkTypeRepository(session)
    assert len(await repo.list_active()) == 2
    assert len(await repo.list_tags()) == 2


async def test_an_unmatched_reference_aborts_before_writing_anything(session):
    await seed_project(session, "OFC route", "TELE 22")
    with pytest.raises(DomainValidationError) as exc:
        await service(session).load(parse_seed(seed_payload()))
    assert "NTPC Vindhyachal" in str(exc.value)

    # The first pass must not have landed either: a partial load would look like
    # a successful one on the next run.
    listed = await SqlAlchemyWorkTypeRepository(session).list(PageRequest(limit=50))
    assert listed.total == 0


async def test_types_only_loads_the_first_pass_without_the_portfolio(session):
    outcome = await service(session).load(parse_seed(seed_payload()), types_only=True)

    assert outcome.work_types_created == 2
    assert outcome.aliases_created == 3
    assert outcome.tags_created == 0
    assert outcome.tags_skipped is True
    assert await SqlAlchemyWorkTypeRepository(session).list_tags() == []


async def test_tags_can_be_added_by_a_later_full_run(session):
    payload = parse_seed(seed_payload())
    await service(session).load(payload, types_only=True)
    await seed_portfolio(session)

    outcome = await service(session).load(payload)
    assert outcome.work_types_created == 0  # already present
    assert outcome.tags_created == 2


# --------------------------------------------------------------------------- #
# The known workbook hazards
# --------------------------------------------------------------------------- #
async def test_an_embedded_newline_reconciles_against_a_clean_reference(session):
    await seed_project(session, "OFC route", "TELE 22")
    await seed_project(session, "NTPC LAN revamp", "NTPC Vindhyachal")
    payload = parse_seed(seed_payload(second_projects=("NTPC\nVindhyachal ",)))

    outcome = await service(session).load(payload)
    assert outcome.tags_created == 2


async def test_two_references_collapsing_to_one_key_block_the_load(session):
    await seed_portfolio(session)
    payload = parse_seed(
        seed_payload(projects=("NTPC Vindhyachal",), second_projects=("NTPC\nVindhyachal ",))
    )
    plan = await service(session).plan(payload)
    assert "ntpc vindhyachal" in plan.collisions
    assert not plan.can_load_tags

    with pytest.raises(DomainValidationError):
        await service(session).load(payload)


async def test_one_reference_shared_by_two_work_types_is_fine(session):
    # A project can evidence more than one capability; that is not a collision.
    await seed_project(session, "OFC route", "TELE 22")
    payload = parse_seed(seed_payload(projects=("TELE 22",), second_projects=("TELE 22",)))

    outcome = await service(session).load(payload)
    assert outcome.tags_created == 2


# --------------------------------------------------------------------------- #
# Bookkeeping
# --------------------------------------------------------------------------- #
async def test_the_load_bumps_the_counter_once_and_audits_once(session):
    await seed_portfolio(session)
    versions = SqlAlchemyPortfolioVersionRepository(session)
    before = await versions.current()

    await service(session).load(parse_seed(seed_payload()))

    assert await versions.current() == before + 1
    logs = await SqlAlchemyAuditLogRepository(session).list(PageRequest(limit=50))
    seed_entries = [e for e in logs.items if e.action == "work_type.seed_load"]
    assert len(seed_entries) == 1
    assert seed_entries[0].diff["work_types_created"] == 2
    assert seed_entries[0].diff["tags_created"] == 2
