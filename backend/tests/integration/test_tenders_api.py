"""Phase 3 tender-registry API tests."""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers


async def test_create_and_get_tender(client, app_db):
    headers = await auth_headers(client, app_db)
    resp = await client.post(
        "/tenders",
        json={"tender_number": "T-100", "title": "Road work", "estimated_value": "1500000.50"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["tender_number"] == "T-100"
    assert body["status"] == "REGISTERED"  # lifecycle on every representation
    assert body["estimated_value"] == "1500000.50"

    got = await client.get(f"/tenders/{body['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]


async def test_duplicate_tender_number_conflicts(client, app_db):
    headers = await auth_headers(client, app_db)
    payload = {"tender_number": "T-DUP", "title": "First"}
    assert (await client.post("/tenders", json=payload, headers=headers)).status_code == 201
    dup = await client.post("/tenders", json=payload, headers=headers)
    assert dup.status_code == 409


async def test_list_filters_and_paginates(client, app_db):
    headers = await auth_headers(client, app_db)
    for i in range(3):
        await client.post(
            "/tenders",
            json={"tender_number": f"T-{i}", "title": f"Bridge {i}"},
            headers=headers,
        )
    await client.post(
        "/tenders", json={"tender_number": "X-9", "title": "Road repair"}, headers=headers
    )

    page = await client.get("/tenders", params={"search": "bridge", "limit": 2}, headers=headers)
    body = page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["has_more"] is True

    status_page = await client.get("/tenders", params={"status": "REGISTERED"}, headers=headers)
    assert status_page.json()["total"] == 4


async def test_patch_and_delete(client, app_db):
    headers = await auth_headers(client, app_db)
    created = (
        await client.post(
            "/tenders", json={"tender_number": "T-P", "title": "Old"}, headers=headers
        )
    ).json()

    patched = await client.patch(
        f"/tenders/{created['id']}", json={"title": "New"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "New"

    deleted = await client.delete(f"/tenders/{created['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/tenders/{created['id']}", headers=headers)).status_code == 404


async def test_get_missing_tender_404(client, app_db):
    headers = await auth_headers(client, app_db)
    resp = await client.get("/tenders/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404


# --- RBAC ---
async def test_employee_can_create_and_read(client, app_db):
    # Tender ingestion is an EMPLOYEE capability, inherited from the analyst tier.
    employee = await auth_headers(client, app_db, email="e@example.com", role=UserRole.EMPLOYEE)
    create = await client.post(
        "/tenders", json={"tender_number": "T-V", "title": "X"}, headers=employee
    )
    assert create.status_code == 201
    assert (await client.get("/tenders", headers=employee)).status_code == 200


async def test_unauthenticated_rejected(client):
    assert (await client.get("/tenders")).status_code == 401
