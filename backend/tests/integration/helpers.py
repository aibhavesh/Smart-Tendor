"""Shared helpers for API integration tests.

Sign-in supports Google and manual email/password alike, both over HTTP
(``/auth/google``, ``/auth/register``); the auth-flow tests exercise those
routes directly. Most other tests just need an authenticated caller and don't
care which method it used, so this module seeds the User row directly and
mints an access token for it instead — that deliberately bypasses the
admission gate (the gate has its own dedicated tests in test_auth_api.py), and
every other test would otherwise have to stand up a Google stub or register an
account just to get a bearer token.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from tender_intel.domain.entities import RoleAssignment, User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.infrastructure.repositories.role_assignment_repo import (
    SqlAlchemyRoleAssignmentRepository,
)
from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository
from tender_intel.infrastructure.security.tokens import TokenService


async def seed_user(
    app: FastAPI,
    *,
    email: str = "employee@example.com",
    full_name: str = "Test",
    role: UserRole = UserRole.EMPLOYEE,
    is_active: bool = True,
    hashed_password: str | None = None,
) -> User:
    """Insert a user directly, bypassing both the Google and manual sign-in flows.

    ``hashed_password`` is a pre-hashed value, not a plaintext password — pass
    ``infrastructure.security.passwords.hash_password("...")`` when a test
    needs a seeded account that can also log in manually.
    """
    factory = app.state.test_session_factory
    async with factory() as session:
        repo = SqlAlchemyUserRepository(session)
        created = await repo.add(
            User(
                email=email,
                full_name=full_name,
                role=role,
                is_active=is_active,
                hashed_password=hashed_password,
            )
        )
        await session.commit()
        return created


async def seed_role_assignment(
    app: FastAPI,
    *,
    email: str,
    role: UserRole,
    assigned_by: User | None = None,
) -> RoleAssignment:
    """Insert an unconsumed elevation row directly."""
    factory = app.state.test_session_factory
    async with factory() as session:
        repo = SqlAlchemyRoleAssignmentRepository(session)
        created = await repo.add(
            RoleAssignment(
                email=email.strip().lower(),
                role=role,
                assigned_by=assigned_by.id if assigned_by else None,
            )
        )
        await session.commit()
        return created


async def get_role_assignment(app: FastAPI, email: str) -> RoleAssignment | None:
    factory = app.state.test_session_factory
    async with factory() as session:
        return await SqlAlchemyRoleAssignmentRepository(session).get_by_email(email)


async def get_user_by_email(app: FastAPI, email: str) -> User | None:
    factory = app.state.test_session_factory
    async with factory() as session:
        return await SqlAlchemyUserRepository(session).get_by_email(email)


async def promote(app: FastAPI, email: str, role: UserRole) -> None:
    factory = app.state.test_session_factory
    async with factory() as session:
        repo = SqlAlchemyUserRepository(session)
        user = await repo.get_by_email(email)
        assert user is not None
        user.role = role
        await repo.update(user)
        await session.commit()


def bearer(app: FastAPI, user: User) -> dict[str, str]:
    """Mint an access token for an already-seeded user."""
    tokens = TokenService(app.state.test_settings)
    return {"Authorization": f"Bearer {tokens.create_access_token(user).token}"}


async def auth_headers(
    client: AsyncClient,
    app: FastAPI,
    *,
    email: str = "employee@example.com",
    role: UserRole = UserRole.EMPLOYEE,
) -> dict[str, str]:
    """Seed a user at ``role`` and return an Authorization header for them."""
    user = await seed_user(app, email=email, role=role)
    return bearer(app, user)
