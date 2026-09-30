"""Phase 5 past-project API tests."""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers


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
    first = await client.post("/projects", json={"name": "First"}, headers=manager)
    second = await client.post("/projects", json={"name": "Second"}, headers=manager)

    response = await client.delete("/projects", headers=manager)
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
    assert (await client.get("/projects", headers=manager)).json()["total"] == 0


async def test_delete_all_requires_a_manager(client, app_db):
    employee = await auth_headers(client, app_db, email="employee@example.com", role=UserRole.EMPLOYEE)
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


async def test_tender_matches_endpoint(client, app_db):
    headers = await auth_headers(client, app_db)
    await client.post(
        "/projects",
        json={"name": "Road construction highway", "work_value": "20000000"},
        headers=headers,
    )
    tender = (
        await client.post(
            "/tenders",
            json={"tender_number": "T-MATCH", "title": "Road construction"},
            headers=headers,
        )
    ).json()

    resp = await client.get(f"/tenders/{tender['id']}/matches", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["name"] == "Road construction highway"
