"""JWT issuing/verification and refresh-token hashing.

Two token types are issued from the same signing secret, distinguished by a
``type`` claim so an access token can never be replayed as a refresh token:

* ``access``  — 15 min (default), carries the role for cheap RBAC checks.
* ``refresh`` — 7 days (default), exchanged for a new pair; the *hash* of the
  token is stored in a ``UserSession`` so it can be revoked.

There is no reset token because password-reset endpoints are not implemented.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt

from tender_intel.core.config import Settings
from tender_intel.domain.entities import User
from tender_intel.domain.exceptions import InvalidTokenError


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str  # user id
    token_type: TokenType
    role: str | None
    jti: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    expires_at: datetime


def hash_refresh_token(token: str) -> str:
    """Deterministic hash stored in UserSession (never store the raw token)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret
        self._algorithm = settings.jwt_algorithm
        self._access_ttl = timedelta(minutes=settings.access_token_ttl_minutes)
        self._refresh_ttl = timedelta(days=settings.refresh_token_ttl_days)

    def _issue(self, user: User, token_type: TokenType, ttl: timedelta) -> IssuedToken:
        now = datetime.now(UTC)
        expires_at = now + ttl
        payload = {
            "sub": str(user.id),
            "type": token_type.value,
            "role": user.role.value,
            "jti": uuid.uuid4().hex,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return IssuedToken(token=token, expires_at=expires_at)

    def create_access_token(self, user: User) -> IssuedToken:
        return self._issue(user, TokenType.ACCESS, self._access_ttl)

    def create_refresh_token(self, user: User) -> IssuedToken:
        return self._issue(user, TokenType.REFRESH, self._refresh_ttl)

    def decode(self, token: str, expected_type: TokenType) -> TokenClaims:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(str(exc)) from exc
        if payload.get("type") != expected_type.value:
            raise InvalidTokenError(f"expected {expected_type.value} token")
        return TokenClaims(
            subject=payload["sub"],
            token_type=expected_type,
            role=payload.get("role"),
            jti=payload.get("jti", ""),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
