"""User and UserSession entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tender_intel.domain.enums.roles import UserRole


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class User:
    """A platform account.

    Sign-in supports two independent methods: Google (``google_sub`` set) and
    email/password (``hashed_password`` set). Neither is required by the
    other — an account may hold one, the other, or both once linked — but the
    admission gate (organisation domain, or an individually excepted address)
    applies to every account-creation path alike. ``email`` is always stored
    normalised (trimmed, lowercased) by that gate.
    """

    email: str
    full_name: str
    role: UserRole = UserRole.EMPLOYEE
    google_sub: str | None = None  # Google subject identifier, if linked
    hashed_password: str | None = None  # PBKDF2 hash, if manual sign-in is set up
    is_active: bool = True
    last_login_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def can_act_as(self, required: UserRole) -> bool:
        return self.is_active and self.role.can_act_as(required)

    def is_exactly(self, *roles: UserRole) -> bool:
        """True when this active user holds one of ``roles`` exactly.

        Used where a capability must *not* be inherited by higher tiers — the
        bid verdict, which belongs to MANAGER and SUPER_ADMIN but not ADMIN.
        """
        return self.is_active and self.role in roles


@dataclass(slots=True)
class UserSession:
    user_id: UUID
    refresh_token_hash: str
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    revoked_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > _now()

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = _now()
