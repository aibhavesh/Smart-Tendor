"""Eligibility screening over HTTP (feature spec §8).

Covers the three outcomes end to end, the role gates, staleness, and the
invariant that an unconfigured platform routes tenders to a person rather than
refusing them all.
"""

from __future__ import annotations

from datetime import date

import pytest

from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.enums.work_type import WorkTypeCategory
from tender_intel.domain.services.financial_year import completed_years_before
from tests.integration.helpers import auth_headers

CLOSING = date(2026, 12, 1)
CERT = date(2024, 6, 1)
EV = "5000000"  # 50 lakh
BASE = "/api/v1"

DOC = (
    b"Name of Work: RCC Road resurfacing\n"
    b"Estimated Cost: Rs. 50 lakh\n"
    b"Completion Period: 12 months\n"
    b"Last Date of Submission: 01/12/2026\n"
    b"Scope of Work: Construction of RCC road\n"
)


async def _admin(client, app):
    return await auth_headers(client, app, email="admin@example.com", role=UserRole.ADMIN)


async def _seed_taxonomy(client, headers) -> str:
    created = await client.post(
        f"{BASE}/work-types",
        json={
            "code": "RCC_ROAD",
            "name": "RCC road works",
            "category": WorkTypeCategory.TELECOM_NETWORKING.value,
        },
        headers=headers,
    )
    assert created.status_code == 201
    work_type_id = created.json()["id"]
    alias = await client.post(
        f"{BASE}/work-types/{work_type_id}/aliases",
        json={"alias": "rcc road", "kind": "SYNONYM"},
        headers=headers,
    )
    assert alias.status_code == 201
    return work_type_id


async def _seed_turnover(client, headers, amount: str = "10000000") -> None:
    for year in completed_years_before(CLOSING, 3):
        response = await client.post(
            f"{BASE}/company-turnover",
            json={"financial_year": year.label, "contractual_turnover": amount},
            headers=headers,
        )
        assert response.status_code == 201


async def _seed_project(client, headers, work_type_id: str, value: str = EV) -> str:
    project = await client.post(
        "/projects",
        json={
            "name": "RCC road resurfacing, Indore",
            "work_value": value,
            "description": "Construction of RCC road",
            "completion_certificate_date": CERT.isoformat(),
        },
        headers=headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]
    tagged = await client.post(
        f"{BASE}/projects/{project_id}/work-types",
        json={"work_type_id": work_type_id, "source": "SEED"},
        headers=headers,
    )
    assert tagged.status_code == 201
    return project_id


async def _parsed_tender(client, headers) -> str:
    tender = await client.post(
        "/tenders",
        json={"tender_number": "T-ELIG", "title": "RCC Road resurfacing"},
        headers=headers,
    )
    tender_id = tender.json()["id"]
    await client.post(
        f"/tenders/{tender_id}/documents/upload",
        files={"file": ("t.txt", DOC, "text/plain")},
        headers=headers,
    )
    await client.post(f"/tenders/{tender_id}/extract", headers=headers)
    return tender_id


# --------------------------------------------------------------------------- #
# The three outcomes
# --------------------------------------------------------------------------- #
async def test_eligible_end_to_end(client, app_db):
    headers = await _admin(client, app_db)
    work_type_id = await _seed_taxonomy(client, headers)
    await _seed_turnover(client, headers)
    await _seed_project(client, headers, work_type_id)
    tender_id = await _parsed_tender(client, headers)

    response = await client.post(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ELIGIBLE"
    assert body["financial_pass"] is True
    assert body["technical_pass"] is True
    assert body["rule_satisfied"] == "1x60"
    assert body["reasons"] == []
    assert [m["code"] for m in body["matched_work_types"]] == ["RCC_ROAD"]
    # FR-304: the qualifying project is named, not just counted.
    assert body["qualifying_projects"][0]["name"].startswith("RCC road resurfacing")


async def test_not_eligible_when_turnover_falls_short(client, app_db):
    headers = await _admin(client, app_db)
    work_type_id = await _seed_taxonomy(client, headers)
    await _seed_turnover(client, headers, amount="1")
    await _seed_project(client, headers, work_type_id)
    tender_id = await _parsed_tender(client, headers)

    body = (await client.post(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)).json()
    assert body["status"] == "NOT_ELIGIBLE"
    assert body["financial_pass"] is False
    assert any("below the required" in r for r in body["reasons"])


async def test_indeterminate_when_turnover_is_missing(client, app_db):
    headers = await _admin(client, app_db)
    work_type_id = await _seed_taxonomy(client, headers)
    await _seed_project(client, headers, work_type_id)
    tender_id = await _parsed_tender(client, headers)

    body = (await client.post(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)).json()
    assert body["status"] == "INDETERMINATE"
    assert body["financial_pass"] is None
    assert any("completed financial years" in r for r in body["reasons"])


async def test_empty_turnover_routes_to_review_not_refusal(client, app_db):
    """The invariant rule 1b exists to protect.

    With nothing configured, every tender must reach a person. Grouping
    indeterminate under NOT_ELIGIBLE instead would return NO_BID for the whole
    portfolio until an administrator has entered three years of figures.
    """
    headers = await _admin(client, app_db)
    tender_id = await _parsed_tender(client, headers)

    screened = await client.post(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)
    assert screened.json()["status"] == "INDETERMINATE"

    analyzed = await client.post(f"/tenders/{tender_id}/analyze", headers=headers)
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["recommendation"]["verdict"] == "REVIEW"
    assert body["qualification"]["status"] == "INDETERMINATE"
    assert body["recommendation"]["win_probability"] > 0


# --------------------------------------------------------------------------- #
# Reading, staleness and gates
# --------------------------------------------------------------------------- #
async def test_reading_before_screening_is_404(client, app_db):
    headers = await _admin(client, app_db)
    tender_id = await _parsed_tender(client, headers)
    assert (
        await client.get(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)
    ).status_code == 404


async def test_a_fresh_result_is_not_stale(client, app_db):
    headers = await _admin(client, app_db)
    work_type_id = await _seed_taxonomy(client, headers)
    await _seed_turnover(client, headers)
    await _seed_project(client, headers, work_type_id)
    tender_id = await _parsed_tender(client, headers)

    await client.post(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)
    read = await client.get(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)
    assert read.json()["is_stale"] is False


async def test_a_portfolio_change_makes_a_result_stale(client, app_db):
    headers = await _admin(client, app_db)
    work_type_id = await _seed_taxonomy(client, headers)
    await _seed_turnover(client, headers)
    await _seed_project(client, headers, work_type_id)
    tender_id = await _parsed_tender(client, headers)
    await client.post(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)

    # Any taxonomy mutation bumps the counter the fingerprint reads.
    await client.post(
        f"{BASE}/work-types",
        json={"code": "OTHER", "name": "Other", "category": "SIGNALLING"},
        headers=headers,
    )

    read = await client.get(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)
    assert read.json()["is_stale"] is True


async def test_screening_an_unparsed_tender_is_refused(client, app_db):
    headers = await _admin(client, app_db)
    tender = await client.post(
        "/tenders", json={"tender_number": "T-RAW", "title": "X"}, headers=headers
    )
    response = await client.post(
        f"{BASE}/tenders/{tender.json()['id']}/eligibility", headers=headers
    )
    # 422, consistent with every other endpoint in this API.
    assert response.status_code == 422


async def test_anonymous_is_refused(client, app_db):
    headers = await _admin(client, app_db)
    tender_id = await _parsed_tender(client, headers)
    assert (await client.post(f"{BASE}/tenders/{tender_id}/eligibility")).status_code == 401


@pytest.mark.parametrize("role", [UserRole.EMPLOYEE, UserRole.MANAGER, UserRole.ADMIN])
async def test_every_role_at_level_20_and_above_may_screen(client, app_db, role):
    admin = await _admin(client, app_db)
    tender_id = await _parsed_tender(client, admin)
    headers = await auth_headers(
        client, app_db, email=f"screener-{role.value.lower()}@example.com", role=role
    )
    assert (
        await client.post(f"{BASE}/tenders/{tender_id}/eligibility", headers=headers)
    ).status_code == 200
