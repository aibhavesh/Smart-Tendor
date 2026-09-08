"""Phase 2 security-primitive tests: JWT lifecycle, password hashing, and the
RBAC dependencies.
"""

from __future__ import annotations

import pytest

from tender_intel.core.config import Environment, Settings
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.exceptions import InvalidTokenError, PermissionDeniedError
from tender_intel.infrastructure.security.passwords import hash_password, verify_password
from tender_intel.infrastructure.security.tokens import (
    TokenService,
    TokenType,
    hash_refresh_token,
)


# --- Password hashing ---
def test_password_hash_roundtrips():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", hashed) is True


def test_password_hash_rejects_wrong_password():
    hashed = hash_password("correct-horse-battery")
    assert verify_password("wrong-password", hashed) is False


def test_password_hash_never_stores_the_plaintext():
    hashed = hash_password("correct-horse-battery")
    assert "correct-horse-battery" not in hashed


def test_password_hash_uses_a_fresh_salt_each_time():
    first = hash_password("correct-horse-battery")
    second = hash_password("correct-horse-battery")
    assert first != second  # different salts -> different stored strings
    assert verify_password("correct-horse-battery", first) is True
    assert verify_password("correct-horse-battery", second) is True


def test_verify_password_fails_closed_on_garbage_input():
    assert verify_password("anything", "not-a-hash") is False
    assert verify_password("anything", "") is False


def _settings(**kw) -> Settings:
    base = {
        "environment": Environment.CI,
        "jwt_secret": "test-secret-value-that-is-long-enough-1234",
    }
    return Settings(**{**base, **kw})


# --- Tokens ---
def _user() -> User:
    return User(email="a@b.com", full_name="A", role=UserRole.EMPLOYEE)


def test_access_token_roundtrip():
    svc = TokenService(_settings())
    user = _user()
    issued = svc.create_access_token(user)
    claims = svc.decode(issued.token, TokenType.ACCESS)
    assert claims.subject == str(user.id)
    assert claims.role == "EMPLOYEE"
    assert claims.token_type is TokenType.ACCESS


def test_token_type_mismatch_rejected():
    svc = TokenService(_settings())
    refresh = svc.create_refresh_token(_user())
    with pytest.raises(InvalidTokenError):
        svc.decode(refresh.token, TokenType.ACCESS)


def test_tampered_token_rejected():
    svc = TokenService(_settings())
    token = svc.create_access_token(_user()).token
    with pytest.raises(InvalidTokenError):
        svc.decode(token + "x", TokenType.ACCESS)


def test_wrong_secret_rejected():
    issued = TokenService(_settings()).create_access_token(_user())
    other = TokenService(_settings(jwt_secret="a-totally-different-secret-value-abcdef"))
    with pytest.raises(InvalidTokenError):
        other.decode(issued.token, TokenType.ACCESS)


def test_expired_token_rejected():
    svc = TokenService(_settings(access_token_ttl_minutes=-1))  # already expired
    token = svc.create_access_token(_user()).token
    with pytest.raises(InvalidTokenError):
        svc.decode(token, TokenType.ACCESS)


def test_refresh_hash_is_deterministic():
    assert hash_refresh_token("abc") == hash_refresh_token("abc")
    assert hash_refresh_token("abc") != hash_refresh_token("abd")


# --- RBAC dependencies ---
async def test_require_role_enforces_hierarchy():
    from tender_intel.api.dependencies.auth import require_role

    admin_only = require_role(UserRole.ADMIN)
    admin = User(email="admin@b.com", full_name="Admin", role=UserRole.ADMIN)
    employee = User(email="employee@b.com", full_name="Employee", role=UserRole.EMPLOYEE)

    assert await admin_only(user=admin) is admin
    with pytest.raises(PermissionDeniedError):
        await admin_only(user=employee)


async def test_require_exact_roles_does_not_inherit_upward():
    from tender_intel.api.dependencies.auth import require_exact_roles

    verdict = require_exact_roles(UserRole.MANAGER, UserRole.SUPER_ADMIN)
    manager = User(email="m@b.com", full_name="M", role=UserRole.MANAGER)
    root = User(email="s@b.com", full_name="S", role=UserRole.SUPER_ADMIN)
    admin = User(email="a@b.com", full_name="A", role=UserRole.ADMIN)
    employee = User(email="e@b.com", full_name="E", role=UserRole.EMPLOYEE)

    assert await verdict(user=manager) is manager
    assert await verdict(user=root) is root
    # ADMIN outranks MANAGER on level and is still refused — that is the point.
    for denied in (admin, employee):
        with pytest.raises(PermissionDeniedError):
            await verdict(user=denied)


async def test_inactive_user_fails_both_gates():
    from tender_intel.api.dependencies.auth import require_exact_roles, require_role

    dormant = User(email="x@b.com", full_name="X", role=UserRole.SUPER_ADMIN, is_active=False)
    with pytest.raises(PermissionDeniedError):
        await require_role(UserRole.EMPLOYEE)(user=dormant)
    with pytest.raises(PermissionDeniedError):
        await require_exact_roles(UserRole.SUPER_ADMIN)(user=dormant)
