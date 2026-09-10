"""Pydantic request/response schemas for the auth surface.

Sign-in supports both Google (``GoogleLoginRequest`` — the address arrives
inside a Google-verified token, never client-chosen) and manual email/password
(``RegisterRequest`` / ``LoginRequest``). ``EmailStr`` gives the manual routes
the same "is this even a routable address" validation FastAPI already applies
elsewhere; the organisation-domain admission gate is a separate, stricter
check applied by :class:`AuthService`, not by these schemas.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from tender_intel.domain.entities import User
from tender_intel.domain.enums.roles import UserRole


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    # Length only, here: this is "is the credential well-formed", not a
    # strength meter. The frontend confirms the match; the hash is what
    # actually protects the account.
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_entity(cls, user: User) -> UserResponse:
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )
