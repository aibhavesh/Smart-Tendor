"""Authentication and RBAC dependencies.

``get_current_user`` resolves the bearer access token to an active user;
``require_role`` builds a dependency enforcing the four-level hierarchy on a
protected endpoint.

``require_exact_roles`` is the escape hatch for the rare capability that must
*not* be inherited upward — the bid verdict belongs to MANAGER and SUPER_ADMIN,
and an ADMIN sitting at level 40 must not acquire it just by outranking a
manager.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tender_intel.api.dependencies.repositories import get_user_repo
from tender_intel.api.dependencies.services import get_token_service
from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.exceptions import (
    AuthenticationError,
    InactiveUserError,
    InvalidTokenError,
    PermissionDeniedError,
)
from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository
from tender_intel.infrastructure.security.tokens import TokenService, TokenType

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    users: SqlAlchemyUserRepository = Depends(get_user_repo),
    tokens: TokenService = Depends(get_token_service),
) -> User:
    if credentials is None:
        raise AuthenticationError("missing bearer token")
    claims = tokens.decode(credentials.credentials, TokenType.ACCESS)
    user = await users.get(UUID(claims.subject))
    if user is None:
        raise AuthenticationError("user not found")
    if not user.is_active:
        raise InactiveUserError("account is deactivated")
    request.state.user_id = user.id
    return user


def get_optional_subject(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    tokens: TokenService = Depends(get_token_service),
) -> UUID | None:
    """The signed-in user's id when a valid access token is present, else ``None``.

    Never raises, and deliberately never touches the database. This exists to
    *attribute* a request from an endpoint that must also serve anonymous
    callers — it is not an authorisation check and must never be used as one.

    Two consequences of skipping the user lookup, both acceptable for a label
    and neither acceptable for a gate: a token belonging to a since-deleted or
    since-deactivated account still attributes until it expires, and no check is
    made that the subject still exists. Anything that needs to know the user is
    real and active must use :func:`get_current_user`.
    """
    if credentials is None:
        return None
    try:
        claims = tokens.decode(credentials.credentials, TokenType.ACCESS)
        return UUID(claims.subject)
    except (InvalidTokenError, ValueError):
        return None


def require_role(minimum: UserRole) -> Callable[..., Awaitable[User]]:
    """Admit every role at or above ``minimum`` (the normal, inclusive gate)."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if not user.can_act_as(minimum):
            raise PermissionDeniedError(f"requires {minimum.value} (have {user.role.value})")
        return user

    return dependency


def require_exact_roles(*allowed: UserRole) -> Callable[..., Awaitable[User]]:
    """Admit only the listed roles — no inheritance from higher levels."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if not user.is_exactly(*allowed):
            names = " or ".join(r.value for r in allowed)
            raise PermissionDeniedError(f"requires {names} exactly (have {user.role.value})")
        return user

    return dependency
