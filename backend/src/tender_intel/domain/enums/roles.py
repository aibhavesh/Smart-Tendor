"""The four-level role hierarchy (RBAC).

Access is hierarchical and inclusive: an endpoint requiring level *N* admits
every role at or above *N*. ``EMPLOYEE`` is the floor every account is born
with, not a rejection.

Level 10 and the gaps between tiers are deliberately left free for future
insertion — do not renumber. ``EMPLOYEE`` sits at 20 rather than 10 because it
absorbs the full capability set of the former analyst tier.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"

    @property
    def level(self) -> int:
        return _LEVELS[self]

    def can_act_as(self, required: UserRole) -> bool:
        """True when this role is at least as privileged as ``required``."""
        return self.level >= required.level


_LEVELS: dict[UserRole, int] = {
    UserRole.EMPLOYEE: 20,
    UserRole.MANAGER: 30,
    UserRole.ADMIN: 40,
    UserRole.SUPER_ADMIN: 50,
}

#: Roles that may be pre-provisioned against an email address before that
#: person first signs in. ``EMPLOYEE`` is excluded because it is the default
#: every org-domain account already receives — an EMPLOYEE assignment row would
#: carry no information.
ELEVATED_ROLES: frozenset[UserRole] = frozenset(
    {UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN}
)
