"""Pre-provisioned role elevation.

An administrator records the role a named person should receive *before* that
person first signs in. When an account is created for a matching (normalised)
email it is born with that role; every other org-domain address is born
EMPLOYEE.

This is a provisioning artefact only. It is **never** consulted when
authorising a request — that always reads ``User.role``. Once the row is
consumed it stays as history; changing a live user's role is FR-602 against the
User record, not an edit here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tender_intel.domain.enums.roles import ELEVATED_ROLES, UserRole
from tender_intel.domain.exceptions import DomainValidationError


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class RoleAssignment:
    #: Normalised (trimmed, lowercased) address — the same string the admission
    #: gate produces, so the lookup at sign-in cannot miss on casing.
    email: str
    role: UserRole
    #: The administrator who created the row. ``None`` marks a row seeded by
    #: the bootstrap migration, which by definition has no human assigner.
    assigned_by: UUID | None = None
    assigned_at: datetime = field(default_factory=_now)
    consumed_at: datetime | None = None
    consumed_user_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.role not in ELEVATED_ROLES:
            raise DomainValidationError(
                f"{self.role.value} cannot be pre-provisioned: every org-domain account "
                "already receives EMPLOYEE by default"
            )

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def consume(self, user_id: UUID) -> None:
        """Record that an account was created from this assignment."""
        if self.is_consumed:
            raise DomainValidationError("role assignment has already been consumed")
        self.consumed_at = _now()
        self.consumed_user_id = user_id
