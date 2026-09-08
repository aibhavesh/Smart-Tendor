"""Auth-flow tests driven through the real ASGI app.

Two independent sign-in methods, tested side by side: Google (every flow
below that starts from a verified Google identity) and manual email/password
(``/auth/register`` and ``/auth/login``). Both are subject to the same
organisation-domain admission gate, and both must produce a token pair that
works identically against every protected route.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tender_intel.api.dependencies.services import get_google_verifier
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.exceptions import InvalidTokenError
from tender_intel.domain.interfaces.providers import GoogleIdentity
from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository
from tests.integration.conftest import ORG_DOMAIN
from tests.integration.helpers import bearer, get_user_by_email, seed_user

ORG_EMAIL = f"asha@{ORG_DOMAIN}"
OTHER_ORG_EMAIL = f"vikram@{ORG_DOMAIN}"


class _StubVerifier:
    """Returns a fixed identity; ``id_token == "bad"`` fails verification."""

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
            subject="google-sub-123",
            email=ORG_EMAIL,
            full_name="Asha",
            hosted_domain=ORG_DOMAIN,
        ),
    )


async def _sign_in(client, id_token: str = "good"):
    return await client.post("/auth/google", json={"id_token": id_token})


# --- There is still no password-reset flow ---
@pytest.mark.parametrize(
    ("method", "path"), [("post", "/auth/forgot-password"), ("post", "/auth/reset-password")]
)
async def test_reset_routes_do_not_exist(client, method, path):
    resp = await getattr(client, method)(path, json={})
    assert resp.status_code == 404


# --- Google sign-in ---
async def test_sign_in_creates_an_employee(client, app_db, google_identity):
    resp = await _sign_in(client)
    assert resp.status_code == 200

    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == ORG_EMAIL
    assert me.json()["role"] == "EMPLOYEE"


async def test_second_sign_in_reuses_the_account(client, app_db, google_identity):
    assert (await _sign_in(client)).status_code == 200
    assert (await _sign_in(client)).status_code == 200

    admin = bearer(app_db, await seed_user(app_db, email="a@x.com", role=UserRole.ADMIN))
    listing = await client.get("/admin/users", headers=admin)
    emails = [u["email"] for u in listing.json()["items"]]
    assert emails.count(ORG_EMAIL) == 1


async def test_bad_token_401(client, google_identity):
    assert (await _sign_in(client, "bad")).status_code == 401


async def test_existing_account_is_linked_not_duplicated(client, app_db, google_identity):
    existing = await seed_user(app_db, email=ORG_EMAIL, full_name="Asha", role=UserRole.MANAGER)

    resp = await _sign_in(client)
    assert resp.status_code == 200

    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
    )
    # Same row, and the pre-existing role is untouched by sign-in.
    assert me.json()["id"] == str(existing.id)
    assert me.json()["role"] == "MANAGER"

    linked = await get_user_by_email(app_db, ORG_EMAIL)
    assert linked is not None
    assert linked.google_sub == google_identity.subject


# --- Admission gate ---
async def test_non_org_email_is_rejected(client, app_db, google_identity):
    _install(app_db, replace(google_identity, email="outsider@gmail.com", hosted_domain=None))
    resp = await _sign_in(client)
    assert resp.status_code == 403
    assert await get_user_by_email(app_db, "outsider@gmail.com") is None


async def test_hosted_domain_mismatch_is_rejected(client, app_db, google_identity):
    """``hd`` is Google's own assertion, so a mismatch is fatal even when the
    address string looks like an organisation address."""
    _install(app_db, replace(google_identity, hosted_domain="someone-else.com"))
    resp = await _sign_in(client)
    assert resp.status_code == 403
    assert await get_user_by_email(app_db, ORG_EMAIL) is None


async def test_absent_hosted_domain_falls_back_to_the_address(client, app_db, google_identity):
    # A personal Google account carries no `hd`; the address must still qualify.
    _install(app_db, replace(google_identity, hosted_domain=None))
    assert (await _sign_in(client)).status_code == 200


async def test_an_excepted_address_is_admitted_despite_its_hosted_domain(
    client, app_db, google_identity
):
    """The exception must short-circuit the `hd` check, not just the address one.

    An individually excepted person is by definition not on an organisation
    domain, so Google reports *their* employer in `hd`. Checking that first
    would refuse them before the exception was ever consulted — which is the
    bug this test exists to catch.
    """
    outsider = "consultant@elsewhere.com"
    app_db.state.container.settings().allowed_email_exceptions.append(outsider)
    _install(app_db, replace(google_identity, email=outsider, hosted_domain="elsewhere.com"))

    resp = await _sign_in(client)
    assert resp.status_code == 200
    assert (await get_user_by_email(app_db, outsider)) is not None


async def test_a_colleague_of_an_excepted_person_is_still_refused(client, app_db, google_identity):
    """The exception is one address, not their whole email provider."""
    app_db.state.container.settings().allowed_email_exceptions.append("consultant@elsewhere.com")
    _install(
        app_db,
        replace(google_identity, email="someone.else@elsewhere.com", hosted_domain="elsewhere.com"),
    )

    resp = await _sign_in(client)
    assert resp.status_code == 403
    assert await get_user_by_email(app_db, "someone.else@elsewhere.com") is None


async def test_mixed_case_google_email_normalises(client, app_db, google_identity):
    _install(app_db, replace(google_identity, email=f"  AsHa@{ORG_DOMAIN.upper()}  "))
    assert (await _sign_in(client)).status_code == 200

    stored = await get_user_by_email(app_db, ORG_EMAIL)
    assert stored is not None
    assert stored.email == ORG_EMAIL


# --- Manual sign-up ---
async def _register(client, **overrides):
    body = {
        "email": ORG_EMAIL,
        "full_name": "Asha",
        "password": "correct-horse-battery",
        **overrides,
    }
    return await client.post("/auth/register", json=body)


async def test_register_creates_an_employee_and_signs_in(client, app_db):
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == ORG_EMAIL
    assert me.json()["role"] == "EMPLOYEE"


async def test_register_never_stores_the_plaintext_password(client, app_db):
    await _register(client)
    stored = await get_user_by_email(app_db, ORG_EMAIL)
    assert stored is not None
    assert stored.hashed_password is not None
    assert stored.hashed_password != "correct-horse-battery"
    assert "correct-horse-battery" not in stored.hashed_password


async def test_register_rejects_non_org_email(client, app_db):
    resp = await _register(client, email="outsider@gmail.com")
    assert resp.status_code == 403
    assert await get_user_by_email(app_db, "outsider@gmail.com") is None


async def test_register_rejects_duplicate_email(client, app_db):
    assert (await _register(client)).status_code == 201
    dupe = await _register(client, full_name="Someone Else", password="a-different-password")
    assert dupe.status_code == 409


async def test_register_rejects_an_email_already_used_by_a_google_account(
    client, app_db, google_identity
):
    assert (await client.post("/auth/google", json={"id_token": "good"})).status_code == 200
    resp = await _register(client)
    assert resp.status_code == 409


async def test_register_rejects_short_password(client):
    resp = await _register(client, password="short1")
    assert resp.status_code == 422


async def test_register_rejects_malformed_email(client):
    resp = await _register(client, email="not-an-email")
    assert resp.status_code == 422


# --- Manual login ---
async def test_login_with_correct_credentials(client, app_db):
    await _register(client)
    resp = await client.post(
        "/auth/login", json={"email": ORG_EMAIL, "password": "correct-horse-battery"}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_rejects_wrong_password(client, app_db):
    await _register(client)
    resp = await client.post("/auth/login", json={"email": ORG_EMAIL, "password": "wrong-password"})
    assert resp.status_code == 401


async def test_login_rejects_unknown_email(client):
    resp = await client.post(
        "/auth/login", json={"email": OTHER_ORG_EMAIL, "password": "whatever-it-is"}
    )
    assert resp.status_code == 401


async def test_login_rejects_a_google_only_account(client, app_db, google_identity):
    """An account with no password (Google-only) must not be logged into manually."""
    assert (await client.post("/auth/google", json={"id_token": "good"})).status_code == 200
    resp = await client.post(
        "/auth/login", json={"email": ORG_EMAIL, "password": "anything-at-all"}
    )
    assert resp.status_code == 401


async def test_login_rejects_deactivated_account(client, app_db):
    await _register(client)
    stored = await get_user_by_email(app_db, ORG_EMAIL)
    assert stored is not None
    stored.is_active = False
    factory = app_db.state.test_session_factory
    async with factory() as session:
        await SqlAlchemyUserRepository(session).update(stored)
        await session.commit()

    resp = await client.post(
        "/auth/login", json={"email": ORG_EMAIL, "password": "correct-horse-battery"}
    )
    assert resp.status_code == 403


async def test_registered_account_can_also_link_google_later(client, app_db):
    """Manual and Google sign-in coexist: registering first does not block linking Google after."""
    assert (await _register(client)).status_code == 201

    _install(
        app_db,
        GoogleIdentity(
            subject="google-sub-999", email=ORG_EMAIL, full_name="Asha", hosted_domain=ORG_DOMAIN
        ),
    )
    resp = await client.post("/auth/google", json={"id_token": "good"})
    assert resp.status_code == 200

    stored = await get_user_by_email(app_db, ORG_EMAIL)
    assert stored is not None
    assert stored.google_sub == "google-sub-999"
    assert stored.hashed_password is not None  # the password still works too


# --- Refresh rotation & logout ---
async def test_refresh_rotates_and_invalidates_old(client, google_identity):
    tokens = (await _sign_in(client)).json()

    first = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    assert first.json()["refresh_token"] != tokens["refresh_token"]

    replay = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


async def test_logout_revokes_refresh(client, google_identity):
    tokens = (await _sign_in(client)).json()

    logout = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout.status_code == 204

    resp = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


async def test_deactivated_account_cannot_sign_in(client, app_db, google_identity):
    await seed_user(app_db, email=ORG_EMAIL, role=UserRole.EMPLOYEE, is_active=False)
    assert (await _sign_in(client)).status_code == 403


# --- /auth/me ---
async def test_me_requires_token(client):
    assert (await client.get("/auth/me")).status_code == 401


async def test_me_rejects_garbage_token(client):
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
