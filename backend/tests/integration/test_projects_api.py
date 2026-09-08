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


async def test_create_from_document_extracts_attributes(client, app_db):
    headers = await auth_headers(client, app_db)
    doc = b"Name of Work: Metro Rail Phase 2\nEstimated Cost: Rs. 5 Crore\nLocation: Indore\n"
    resp = await client.post(
        "/projects/from-document",
        files={"file": ("project.txt", doc, "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Metro Rail Phase 2"
    assert body["work_value"] == "50000000.00"
    assert body["location"] == "Indore"


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
