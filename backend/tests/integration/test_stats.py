"""Operational statistics endpoint — available to any authenticated user."""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers


async def _register_tender(client, headers, number: str) -> str:
    resp = await client.post(
        "/tenders",
        json={"tender_number": number, "title": f"Tender {number}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_stats_requires_authentication(client):
    resp = await client.get("/stats")
    assert resp.status_code == 401


async def test_employee_can_read_operational_stats(client, app_db):
    # The point of the endpoint: the lowest role can read it. /admin/stats cannot.
    viewer = await auth_headers(client, app_db, email="viewer@x.com", role=UserRole.EMPLOYEE)

    resp = await client.get("/stats", headers=viewer)
    assert resp.status_code == 200

    body = resp.json()
    assert set(body) == {
        "tenders_total",
        "tenders_by_status",
        "past_projects_total",
        "reviews_pending",
    }
    # No user or account figures leak through this surface.
    assert "users_total" not in body
    assert "users_by_role" not in body

    forbidden = await client.get("/admin/stats", headers=viewer)
    assert forbidden.status_code == 403


async def test_counts_track_registered_tenders(client, app_db):
    analyst = await auth_headers(client, app_db, email="analyst@x.com", role=UserRole.EMPLOYEE)

    before = (await client.get("/stats", headers=analyst)).json()

    await _register_tender(client, analyst, "NIT/2026/9001")
    await _register_tender(client, analyst, "NIT/2026/9002")

    after = (await client.get("/stats", headers=analyst)).json()

    assert after["tenders_total"] == before["tenders_total"] + 2
    assert after["tenders_by_status"]["REGISTERED"] == (
        before["tenders_by_status"].get("REGISTERED", 0) + 2
    )
    # Newly registered tenders are not analysed, so the review queue is unchanged.
    assert after["reviews_pending"] == before["reviews_pending"]


async def test_totals_agree_with_the_paginated_list(client, app_db):
    """The endpoint must not drift from the per-status counting it replaces."""
    analyst = await auth_headers(client, app_db, email="analyst@x.com", role=UserRole.EMPLOYEE)
    await _register_tender(client, analyst, "NIT/2026/9003")

    stats = (await client.get("/stats", headers=analyst)).json()

    listing = await client.get("/tenders", params={"limit": 1}, headers=analyst)
    assert listing.json()["total"] == stats["tenders_total"]

    registered = await client.get(
        "/tenders", params={"status": "REGISTERED", "limit": 1}, headers=analyst
    )
    assert registered.json()["total"] == stats["tenders_by_status"].get("REGISTERED", 0)


async def test_reviews_pending_matches_the_queue(client, app_db):
    """reviews_pending and GET /reviews/pending share one definition."""
    manager = await auth_headers(client, app_db, email="manager@x.com", role=UserRole.MANAGER)

    stats = (await client.get("/stats", headers=manager)).json()
    queue = await client.get("/reviews/pending", params={"limit": 1}, headers=manager)

    assert queue.status_code == 200
    assert queue.json()["total"] == stats["reviews_pending"]
