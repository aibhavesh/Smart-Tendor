"""Taxonomy and certified-turnover administration (feature spec §8).

Mutations are ADMIN, reads of the taxonomy are level 20, turnover is ADMIN
throughout. Work types deactivate rather than delete, and every mutation is
audited.
"""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers

BASE = "/api/v1"
TYPE = {"code": "OFC_CABLE_SUPPLY", "name": "OFC supply", "category": "TELECOM_NETWORKING"}


async def _admin(client, app):
    return await auth_headers(client, app, email="admin@example.com", role=UserRole.ADMIN)


async def _employee(client, app):
    return await auth_headers(client, app, email="employee@example.com", role=UserRole.EMPLOYEE)


async def _create(client, headers, **overrides) -> dict:
    response = await client.post(f"{BASE}/work-types", json={**TYPE, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Work types
# --------------------------------------------------------------------------- #
async def test_admin_creates_and_reads_back(client, app_db):
    headers = await _admin(client, app_db)
    created = await _create(client, headers)
    assert created["is_active"] is True

    listed = await client.get(f"{BASE}/work-types", headers=headers)
    assert [w["code"] for w in listed.json()["items"]] == ["OFC_CABLE_SUPPLY"]


async def test_a_duplicate_code_conflicts(client, app_db):
    headers = await _admin(client, app_db)
    await _create(client, headers)
    again = await client.post(f"{BASE}/work-types", json=TYPE, headers=headers)
    assert again.status_code == 409


async def test_deactivate_never_deletes(client, app_db):
    headers = await _admin(client, app_db)
    created = await _create(client, headers)

    response = await client.post(f"{BASE}/work-types/{created['id']}/deactivate", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Still readable: a tag on a past project is evidence, and deleting the type
    # would erase why a tender matched.
    still_there = await client.get(f"{BASE}/work-types/{created['id']}", headers=headers)
    assert still_there.status_code == 200


async def test_filters_by_active_and_category(client, app_db):
    headers = await _admin(client, app_db)
    live = await _create(client, headers)
    await _create(client, headers, code="MSDAC", name="Axle counter", category="SIGNALLING")
    await client.post(f"{BASE}/work-types/{live['id']}/deactivate", headers=headers)

    active = await client.get(f"{BASE}/work-types?is_active=true", headers=headers)
    assert [w["code"] for w in active.json()["items"]] == ["MSDAC"]

    signalling = await client.get(f"{BASE}/work-types?category=SIGNALLING", headers=headers)
    assert [w["code"] for w in signalling.json()["items"]] == ["MSDAC"]


async def test_an_employee_may_read_but_not_mutate(client, app_db):
    admin = await _admin(client, app_db)
    await _create(client, admin)
    headers = await _employee(client, app_db)

    assert (await client.get(f"{BASE}/work-types", headers=headers)).status_code == 200
    refused = await client.post(
        f"{BASE}/work-types", json={**TYPE, "code": "OTHER"}, headers=headers
    )
    assert refused.status_code == 403


# --------------------------------------------------------------------------- #
# Aliases
# --------------------------------------------------------------------------- #
async def test_alias_normalisation_is_stored(client, app_db):
    headers = await _admin(client, app_db)
    created = await _create(client, headers)
    alias = await client.post(
        f"{BASE}/work-types/{created['id']}/aliases",
        json={"alias": "  Optical  Fibre Cable ", "kind": "EXPANSION"},
        headers=headers,
    )
    assert alias.status_code == 201
    assert alias.json()["normalised"] == "optical fibre cable"


async def test_a_colliding_alias_is_refused_across_work_types(client, app_db):
    headers = await _admin(client, app_db)
    first = await _create(client, headers)
    second = await _create(client, headers, code="PIJF_CABLE", name="PIJF")

    await client.post(
        f"{BASE}/work-types/{first['id']}/aliases",
        json={"alias": "cable", "kind": "SYNONYM"},
        headers=headers,
    )
    clash = await client.post(
        f"{BASE}/work-types/{second['id']}/aliases",
        json={"alias": "CABLE", "kind": "SYNONYM"},
        headers=headers,
    )
    # Uniqueness is global: two types behind one alias would make the exact
    # stage of the cascade non-deterministic.
    assert clash.status_code == 409


async def test_hyphenated_and_plain_forms_coexist(client, app_db):
    headers = await _admin(client, app_db)
    created = await _create(client, headers, code="WIFI_PROVISION", name="Wi-Fi")
    for alias in ("wi-fi", "wifi"):
        response = await client.post(
            f"{BASE}/work-types/{created['id']}/aliases",
            json={"alias": alias, "kind": "VARIANT"},
            headers=headers,
        )
        assert response.status_code == 201, alias


async def test_an_alias_can_be_removed(client, app_db):
    headers = await _admin(client, app_db)
    created = await _create(client, headers)
    alias = await client.post(
        f"{BASE}/work-types/{created['id']}/aliases",
        json={"alias": "ofc", "kind": "ABBREVIATION"},
        headers=headers,
    )
    removed = await client.delete(
        f"{BASE}/work-types/{created['id']}/aliases/{alias.json()['id']}", headers=headers
    )
    assert removed.status_code == 204


# --------------------------------------------------------------------------- #
# Project tags
# --------------------------------------------------------------------------- #
async def test_tagging_a_project(client, app_db):
    headers = await _admin(client, app_db)
    work_type = await _create(client, headers)
    project = await client.post(
        "/projects", json={"name": "OFC route", "work_value": "100000"}, headers=headers
    )
    project_id = project.json()["id"]

    tagged = await client.post(
        f"{BASE}/projects/{project_id}/work-types",
        json={"work_type_id": work_type["id"], "source": "MANUAL", "evidence": "OFC route"},
        headers=headers,
    )
    assert tagged.status_code == 201
    assert tagged.json()["evidence"] == "OFC route"

    untagged = await client.delete(
        f"{BASE}/projects/{project_id}/work-types/{work_type['id']}", headers=headers
    )
    assert untagged.status_code == 204


async def test_a_deactivated_type_cannot_be_tagged(client, app_db):
    headers = await _admin(client, app_db)
    work_type = await _create(client, headers)
    await client.post(f"{BASE}/work-types/{work_type['id']}/deactivate", headers=headers)
    project = await client.post("/projects", json={"name": "P"}, headers=headers)

    refused = await client.post(
        f"{BASE}/projects/{project.json()['id']}/work-types",
        json={"work_type_id": work_type["id"]},
        headers=headers,
    )
    assert refused.status_code == 422


# --------------------------------------------------------------------------- #
# Certified turnover
# --------------------------------------------------------------------------- #
async def test_turnover_record_and_amend(client, app_db):
    headers = await _admin(client, app_db)
    created = await client.post(
        f"{BASE}/company-turnover",
        json={"financial_year": "2024-25", "contractual_turnover": "1000000"},
        headers=headers,
    )
    assert created.status_code == 201

    amended = await client.patch(
        f"{BASE}/company-turnover/2024-25",
        json={"contractual_turnover": "2000000"},
        headers=headers,
    )
    assert amended.status_code == 200
    assert amended.json()["contractual_turnover"] == "2000000.00"


async def test_a_duplicate_financial_year_conflicts(client, app_db):
    headers = await _admin(client, app_db)
    body = {"financial_year": "2024-25", "contractual_turnover": "1"}
    await client.post(f"{BASE}/company-turnover", json=body, headers=headers)
    again = await client.post(f"{BASE}/company-turnover", json=body, headers=headers)
    assert again.status_code == 409


async def test_a_malformed_financial_year_is_refused(client, app_db):
    headers = await _admin(client, app_db)
    response = await client.post(
        f"{BASE}/company-turnover",
        json={"financial_year": "2024-99", "contractual_turnover": "1"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_turnover_is_admin_only(client, app_db):
    headers = await _employee(client, app_db)
    assert (await client.get(f"{BASE}/company-turnover", headers=headers)).status_code == 403


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
async def test_every_mutation_is_audited(client, app_db):
    headers = await _admin(client, app_db)
    created = await _create(client, headers)
    await client.post(
        f"{BASE}/work-types/{created['id']}/aliases",
        json={"alias": "ofc", "kind": "ABBREVIATION"},
        headers=headers,
    )
    await client.post(
        f"{BASE}/company-turnover",
        json={"financial_year": "2024-25", "contractual_turnover": "1"},
        headers=headers,
    )

    logs = await client.get("/admin/audit-logs?limit=50", headers=headers)
    actions = {entry["action"] for entry in logs.json()["items"]}
    assert {"work_type.create", "work_type.alias_add", "company_turnover.record"} <= actions
