"""Phase 5 past-project API tests."""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers

# A tender document the rule-based extractor can read: it yields an estimated cost
# and a closing date, which is what the similar-work value test needs.
_DOC = (
    b"Name of Work: RCC Road resurfacing\n"
    b"Estimated Cost: Rs. 50 lakh\n"
    b"Completion Period: 12 months\n"
    b"Last Date of Submission: 01/12/2026\n"
    b"Scope of Work: Construction of RCC road\n"
)


async def test_project_crud(client, app_db):
    headers = await auth_headers(client, app_db)
    created = await client.post(
        "/projects",
        json={"name": "Highway widening", "work_value": "25000000", "category": "Roads"},
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Highway widening"
    assert body["embedding_indexed"] is True

    got = await client.get(f"/projects/{body['id']}", headers=headers)
    assert got.status_code == 200

    patched = await client.patch(
        f"/projects/{body['id']}", json={"category": "Highways"}, headers=headers
    )
    assert patched.json()["category"] == "Highways"

    listing = await client.get("/projects", headers=headers)
    assert listing.json()["total"] == 1

    deleted = await client.delete(f"/projects/{body['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/projects/{body['id']}", headers=headers)).status_code == 404


async def test_manager_can_delete_all_projects(client, app_db):
    manager = await auth_headers(client, app_db, email="manager@example.com", role=UserRole.MANAGER)
    await client.post("/projects", json={"name": "First"}, headers=manager)
    await client.post("/projects", json={"name": "Second"}, headers=manager)

    response = await client.delete("/projects", headers=manager)
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
    assert (await client.get("/projects", headers=manager)).json()["total"] == 0


async def test_delete_all_requires_a_manager(client, app_db):
    employee = await auth_headers(
        client, app_db, email="employee@example.com", role=UserRole.EMPLOYEE
    )
    response = await client.delete("/projects", headers=employee)
    assert response.status_code == 403


async def test_document_project_creation_endpoint_is_not_exposed(client, app_db):
    headers = await auth_headers(client, app_db)
    resp = await client.post(
        "/projects/from-document",
        headers=headers,
    )
    # ``/projects/{project_id}`` still owns the path shape for reads/updates,
    # so a removed POST route is correctly rejected as method-not-allowed.
    assert resp.status_code == 405


async def test_employee_can_create_project(client, app_db):
    # EMPLOYEE absorbs the former analyst capability set: project writes are
    # part of it, so the floor role is admitted rather than refused.
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    resp = await client.post("/projects", json={"name": "X"}, headers=employee)
    assert resp.status_code == 201


async def test_backfill_requires_admin(client, app_db):
    employee = await auth_headers(client, app_db, email="a@example.com", role=UserRole.EMPLOYEE)
    assert (await client.post("/projects/backfill", headers=employee)).status_code == 403

    admin = await auth_headers(client, app_db, email="admin@example.com", role=UserRole.ADMIN)
    resp = await client.post("/projects/backfill", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["indexed"] == 0  # everything already indexed on write


async def test_a_screened_tender_surfaces_its_qualifying_projects(client, app_db):
    """The corpus is reachable from a tender through screening, not a separate call.

    There is no standalone ``/tenders/{id}/matches`` endpoint; matching lives
    inside the eligibility screen, which returns the projects that satisfied the
    similar-work value rule. This asserts the corpus is actually consulted.
    """
    # Work-type taxonomy is ADMIN-only to mutate, so this test signs in at that
    # level; every other assertion below still holds at EMPLOYEE.
    headers = await auth_headers(client, app_db, email="admin@example.com", role=UserRole.ADMIN)

    # Stage B only pools a project that carries a work type, a work value and a
    # completion certificate date inside the lookback window, so all three are
    # seeded here — otherwise the pool is empty and the assertion would pass for
    # the wrong reason.
    work_type = await client.post(
        "/api/v1/work-types",
        json={
            "code": "RCC_ROAD",
            "name": "RCC road works",
            "category": "TELECOM_NETWORKING",
        },
        headers=headers,
    )
    assert work_type.status_code == 201
    work_type_id = work_type.json()["id"]

    project = await client.post(
        "/projects",
        json={
            "name": "RCC road resurfacing, Indore",
            "work_value": "5000000",
            "description": "Construction of RCC road",
            "completion_certificate_date": "2024-06-01",
        },
        headers=headers,
    )
    assert project.status_code == 201
    tagged = await client.post(
        f"/api/v1/projects/{project.json()['id']}/work-types",
        json={"work_type_id": work_type_id, "source": "SEED"},
        headers=headers,
    )
    assert tagged.status_code == 201

    tender = (
        await client.post(
            "/tenders",
            json={"tender_number": "T-MATCH", "title": "RCC Road resurfacing"},
            headers=headers,
        )
    ).json()
    tender_id = tender["id"]

    uploaded = await client.post(
        f"/tenders/{tender_id}/documents/upload",
        files={"file": ("t.txt", _DOC, "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 201
    assert (await client.post(f"/tenders/{tender_id}/extract", headers=headers)).status_code == 200

    screened = await client.post(f"/api/v1/tenders/{tender_id}/eligibility", headers=headers)
    assert screened.status_code == 200

    body = screened.json()
    qualifying = body["qualifying_projects"]
    # Turnover is never seeded here, so the financial rule is undecided and the
    # result is INDETERMINATE rather than eligible — but the project pool is still
    # built, and the seeded project is in it.
    assert body["status"] == "INDETERMINATE"
    assert [p["name"] for p in qualifying] == ["RCC road resurfacing, Indore"]
    assert qualifying[0]["project_id"] == project.json()["id"]
