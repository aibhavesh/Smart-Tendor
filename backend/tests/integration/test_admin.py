"""Phase 9 administration & audit tests."""

from __future__ import annotations

from tender_intel.domain.enums.roles import UserRole
from tests.integration.helpers import auth_headers, promote, seed_user


async def _seed(app_db, email: str) -> str:
    """Seed a plain EMPLOYEE and return its id.

    Registration no longer exists as an HTTP route, so the row goes in
    directly.
    """
    user = await seed_user(app_db, email=email, full_name="T")
    return str(user.id)


# --- User administration ---
async def test_list_and_get_users(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    uid = await _seed(app_db, "u1@x.com")

    listing = await client.get("/admin/users", headers=admin)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 2  # admin + u1

    got = await client.get(f"/admin/users/{uid}", headers=admin)
    assert got.status_code == 200
    assert got.json()["email"] == "u1@x.com"


async def test_change_role_and_audit(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    uid = await _seed(app_db, "u1@x.com")

    resp = await client.patch(f"/admin/users/{uid}/role", json={"role": "MANAGER"}, headers=admin)
    assert resp.status_code == 200
    assert resp.json()["role"] == "MANAGER"

    logs = await client.get(
        "/admin/audit-logs", params={"action": "user.role_change"}, headers=admin
    )
    assert logs.json()["total"] >= 1
    entry = logs.json()["items"][0]
    assert entry["diff"]["role"]["after"] == "MANAGER"


async def test_admin_cannot_assign_role_above_own(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    uid = await _seed(app_db, "u1@x.com")
    resp = await client.patch(
        f"/admin/users/{uid}/role", json={"role": "SUPER_ADMIN"}, headers=admin
    )
    assert resp.status_code == 403


async def test_admin_cannot_modify_more_privileged_user(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    sid = await _seed(app_db, "super@x.com")
    await promote(app_db, "super@x.com", UserRole.SUPER_ADMIN)
    resp = await client.patch(f"/admin/users/{sid}/role", json={"role": "EMPLOYEE"}, headers=admin)
    assert resp.status_code == 403


async def test_deactivate_revokes_sessions(client, app_db):
    target = await auth_headers(client, app_db, email="t@x.com", role=UserRole.EMPLOYEE)
    tid = (await client.get("/auth/me", headers=target)).json()["id"]
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)

    resp = await client.patch(
        f"/admin/users/{tid}/active", json={"is_active": False}, headers=admin
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # The deactivated user can no longer authenticate.
    assert (await client.get("/auth/me", headers=target)).status_code == 403


async def test_cannot_deactivate_self(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    aid = (await client.get("/auth/me", headers=admin)).json()["id"]
    resp = await client.patch(
        f"/admin/users/{aid}/active", json={"is_active": False}, headers=admin
    )
    assert resp.status_code == 422


async def test_delete_requires_super_admin(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    uid = await _seed(app_db, "u1@x.com")
    assert (await client.delete(f"/admin/users/{uid}", headers=admin)).status_code == 403

    superadmin = await auth_headers(client, app_db, email="s@x.com", role=UserRole.SUPER_ADMIN)
    assert (await client.delete(f"/admin/users/{uid}", headers=superadmin)).status_code == 204
    assert (await client.get(f"/admin/users/{uid}", headers=superadmin)).status_code == 404


async def test_non_admin_forbidden(client, app_db):
    analyst = await auth_headers(client, app_db, email="a@x.com", role=UserRole.EMPLOYEE)
    assert (await client.get("/admin/users", headers=analyst)).status_code == 403
    assert (await client.get("/admin/audit-logs", headers=analyst)).status_code == 403
    assert (await client.get("/admin/stats", headers=analyst)).status_code == 403


# --- Monitoring ---
async def test_platform_stats(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    await client.post("/tenders", json={"tender_number": "T-1", "title": "A"}, headers=admin)
    await client.post("/tenders", json={"tender_number": "T-2", "title": "B"}, headers=admin)

    stats = await client.get("/admin/stats", headers=admin)
    body = stats.json()
    assert body["tenders_total"] == 2
    assert body["tenders_by_status"]["REGISTERED"] == 2
    assert body["users_total"] >= 1
    assert body["users_active"] >= 1


async def test_system_health(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    resp = await client.get("/admin/system-health", headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["healthy"] is True
    names = {c["name"]: c["status"] for c in body["components"]}
    assert names["database"] == "ok"
    assert names["vector_store"] == "ok"
    assert body["host"]["memory_total_mb"] > 0


async def test_api_usage(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    resp = await client.get("/admin/api-usage", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["total_requests"] >= 1
