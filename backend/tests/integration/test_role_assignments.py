"""The pre-provisioned elevation list: admin management, and its effect at sign-in."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tender_intel.api.dependencies.services import get_google_verifier
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.exceptions import InvalidTokenError
from tender_intel.domain.interfaces.providers import GoogleIdentity
from tests.integration.conftest import ORG_DOMAIN
from tests.integration.helpers import (
    auth_headers,
    get_role_assignment,
    seed_role_assignment,
    seed_user,
)

ORG_EMAIL = f"asha@{ORG_DOMAIN}"


class _StubVerifier:
    def __init__(self, identity: GoogleIdentity) -> None:
        self.identity = identity

    async def verify(self, id_token: str) -> GoogleIdentity:
        if id_token == "bad":
            raise InvalidTokenError("bad token")
        return self.identity


def _install(app, identity: GoogleIdentity) -> GoogleIdentity:
    app.dependency_overrides[get_google_verifier] = lambda: _StubVerifier(identity)
    return identity


@pytest.fixture
def google_identity(app_db) -> GoogleIdentity:
    return _install(
        app_db,
        GoogleIdentity(
            subject="google-sub-999",
            email=ORG_EMAIL,
            full_name="Asha",
            hosted_domain=ORG_DOMAIN,
        ),
    )


async def _sign_in(client):
    return await client.post("/auth/google", json={"id_token": "good"})


async def _role_of(client, token_response) -> str:
    me = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
    )
    return me.json()["role"]


# --- Elevation at account creation --- #
async def test_email_on_the_list_is_born_with_that_role(client, app_db, google_identity):
    await seed_role_assignment(app_db, email=ORG_EMAIL, role=UserRole.MANAGER)
    assert await _role_of(client, await _sign_in(client)) == "MANAGER"


async def test_email_not_on_the_list_is_born_employee(client, app_db, google_identity):
    assert await _role_of(client, await _sign_in(client)) == "EMPLOYEE"


async def test_lookup_is_case_insensitive(client, app_db, google_identity):
    await seed_role_assignment(app_db, email=ORG_EMAIL, role=UserRole.ADMIN)
    _install(app_db, replace(google_identity, email=f"  AsHa@{ORG_DOMAIN.upper()}  "))
    assert await _role_of(client, await _sign_in(client)) == "ADMIN"


async def test_assignment_is_marked_consumed(client, app_db, google_identity):
    await seed_role_assignment(app_db, email=ORG_EMAIL, role=UserRole.MANAGER)
    await _sign_in(client)

    consumed = await get_role_assignment(app_db, ORG_EMAIL)
    assert consumed is not None
    assert consumed.is_consumed
    assert consumed.consumed_at is not None
    assert consumed.consumed_user_id is not None


async def test_elevation_is_not_re_evaluated_on_later_sign_ins(client, app_db, google_identity):
    """A row created after the account exists must not touch the live user.

    The list governs birth only; changing a live role is FR-602.
    """
    await _sign_in(client)  # born EMPLOYEE
    await seed_role_assignment(app_db, email=ORG_EMAIL, role=UserRole.SUPER_ADMIN)

    assert await _role_of(client, await _sign_in(client)) == "EMPLOYEE"
    still_unconsumed = await get_role_assignment(app_db, ORG_EMAIL)
    assert still_unconsumed is not None
    assert not still_unconsumed.is_consumed


# --- Admin management --- #
async def test_admin_can_create_and_list(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)

    created = await client.post(
        "/admin/role-assignments",
        json={"email": f"NEW.Manager@{ORG_DOMAIN}", "role": "MANAGER"},
        headers=admin,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == f"new.manager@{ORG_DOMAIN}"  # stored normalised
    assert body["role"] == "MANAGER"
    assert body["is_consumed"] is False

    listing = await client.get("/admin/role-assignments", headers=admin)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


async def test_create_is_audited(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    await client.post(
        "/admin/role-assignments",
        json={"email": f"m@{ORG_DOMAIN}", "role": "MANAGER"},
        headers=admin,
    )

    logs = await client.get(
        "/admin/audit-logs", params={"action": "role_assignment.create"}, headers=admin
    )
    assert logs.json()["total"] == 1
    entry = logs.json()["items"][0]
    assert entry["entity_type"] == "RoleAssignment"
    assert entry["diff"]["role"] == "MANAGER"


async def test_employee_role_is_rejected(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    resp = await client.post(
        "/admin/role-assignments",
        json={"email": f"e@{ORG_DOMAIN}", "role": "EMPLOYEE"},
        headers=admin,
    )
    assert resp.status_code == 422


async def test_non_org_domain_is_rejected(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    resp = await client.post(
        "/admin/role-assignments",
        json={"email": "outsider@gmail.com", "role": "MANAGER"},
        headers=admin,
    )
    assert resp.status_code == 403


async def test_admin_cannot_pre_provision_above_own_role(client, app_db):
    """Without this the list would be a clean bypass of the FR-602 guard."""
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    resp = await client.post(
        "/admin/role-assignments",
        json={"email": f"root@{ORG_DOMAIN}", "role": "SUPER_ADMIN"},
        headers=admin,
    )
    assert resp.status_code == 403

    root = await auth_headers(client, app_db, email="s@x.com", role=UserRole.SUPER_ADMIN)
    allowed = await client.post(
        "/admin/role-assignments",
        json={"email": f"root@{ORG_DOMAIN}", "role": "SUPER_ADMIN"},
        headers=root,
    )
    assert allowed.status_code == 201


async def test_existing_account_is_rejected_with_a_pointer_to_fr602(client, app_db):
    await seed_user(app_db, email=f"live@{ORG_DOMAIN}", role=UserRole.EMPLOYEE)
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)

    resp = await client.post(
        "/admin/role-assignments",
        json={"email": f"live@{ORG_DOMAIN}", "role": "MANAGER"},
        headers=admin,
    )
    assert resp.status_code == 409
    assert "/admin/users/{user_id}/role" in resp.json()["detail"]

    # And the live user's role is untouched.
    listing = await client.get("/admin/users", headers=admin)
    live = next(u for u in listing.json()["items"] if u["email"] == f"live@{ORG_DOMAIN}")
    assert live["role"] == "EMPLOYEE"


async def test_duplicate_assignment_is_rejected(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    payload = {"email": f"m@{ORG_DOMAIN}", "role": "MANAGER"}
    assert (
        await client.post("/admin/role-assignments", json=payload, headers=admin)
    ).status_code == 201
    assert (
        await client.post("/admin/role-assignments", json=payload, headers=admin)
    ).status_code == 409


# --- Revocation --- #
async def test_revoke_unconsumed(client, app_db):
    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    created = await client.post(
        "/admin/role-assignments",
        json={"email": f"m@{ORG_DOMAIN}", "role": "MANAGER"},
        headers=admin,
    )
    aid = created.json()["id"]

    assert (await client.delete(f"/admin/role-assignments/{aid}", headers=admin)).status_code == 204
    assert (await client.get("/admin/role-assignments", headers=admin)).json()["total"] == 0

    logs = await client.get(
        "/admin/audit-logs", params={"action": "role_assignment.revoke"}, headers=admin
    )
    assert logs.json()["total"] == 1


async def test_revoke_consumed_is_rejected(client, app_db, google_identity):
    await seed_role_assignment(app_db, email=ORG_EMAIL, role=UserRole.MANAGER)
    await _sign_in(client)  # consumes it

    admin = await auth_headers(client, app_db, email="admin@x.com", role=UserRole.ADMIN)
    consumed = await get_role_assignment(app_db, ORG_EMAIL)
    assert consumed is not None

    resp = await client.delete(f"/admin/role-assignments/{consumed.id}", headers=admin)
    assert resp.status_code == 409
    assert "/admin/users/{user_id}/role" in resp.json()["detail"]


async def test_employee_cannot_reach_the_elevation_list(client, app_db):
    employee = await auth_headers(client, app_db, email="e@x.com", role=UserRole.EMPLOYEE)
    assert (await client.get("/admin/role-assignments", headers=employee)).status_code == 403
    assert (
        await client.post(
            "/admin/role-assignments",
            json={"email": f"m@{ORG_DOMAIN}", "role": "MANAGER"},
            headers=employee,
        )
    ).status_code == 403
