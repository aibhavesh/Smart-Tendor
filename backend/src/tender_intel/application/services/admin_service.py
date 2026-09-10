"""User administration & audit query (FR-601..FR-604, FR-606).

Enforces the role hierarchy: an actor may not modify a user more privileged than
themselves, nor assign a role above their own. Deactivation revokes the user's
sessions. Every state change writes an audit entry with a diff; the audit log
itself is append-only (queried here, never mutated).

Also owns the pre-provisioned elevation list. The same "never above your own
level" rule applies there: without it, the list would be a clean bypass of the
FR-602 guard, since an ADMIN could pre-provision a SUPER_ADMIN address and sign
in as it.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from tender_intel.core.config import Settings
from tender_intel.domain.entities import AuditLog, RoleAssignment, User
from tender_intel.domain.enums.roles import ELEVATED_ROLES, UserRole
from tender_intel.domain.exceptions import (
    AssignmentConsumedError,
    DomainValidationError,
    DuplicateEntityError,
    EntityNotFoundError,
    LiveUserExistsError,
    PermissionDeniedError,
)
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    RoleAssignmentRepository,
    UserRepository,
    UserSessionRepository,
)
from tender_intel.domain.services.email_domain import assert_org_email
from tender_intel.domain.value_objects.pagination import Page, PageRequest


class AdminService:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: UserSessionRepository,
        assignments: RoleAssignmentRepository,
        audits: AuditLogRepository,
        settings: Settings,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._assignments = assignments
        self._audits = audits
        self._allowed_domains = settings.allowed_email_domains
        self._allowed_exceptions = settings.allowed_email_exceptions

    async def list_users(self, page: PageRequest) -> Page[User]:
        return await self._users.list(page)

    async def get_user(self, user_id: UUID) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise EntityNotFoundError("User", user_id)
        return user

    async def change_role(self, user_id: UUID, new_role: UserRole, *, actor: User) -> User:
        target = await self.get_user(user_id)
        self._require_authority_over(actor, target)
        if new_role.level > actor.role.level:
            raise PermissionDeniedError("cannot assign a role above your own")
        old_role = target.role
        if old_role is new_role:
            return target
        target.role = new_role
        updated = await self._users.update(target)
        await self._audit(
            actor.id,
            "user.role_change",
            user_id,
            {"role": {"before": old_role.value, "after": new_role.value}},
        )
        return updated

    async def set_active(self, user_id: UUID, is_active: bool, *, actor: User) -> User:
        target = await self.get_user(user_id)
        self._require_authority_over(actor, target)
        if target.id == actor.id and not is_active:
            raise DomainValidationError("you cannot deactivate your own account")
        if target.is_active == is_active:
            return target
        target.is_active = is_active
        updated = await self._users.update(target)
        if not is_active:
            await self._revoke_sessions(user_id)
        await self._audit(
            actor.id,
            "user.activate" if is_active else "user.deactivate",
            user_id,
            {"is_active": {"before": not is_active, "after": is_active}},
        )
        return updated

    async def delete_user(self, user_id: UUID, *, actor: User) -> None:
        target = await self.get_user(user_id)
        if target.id == actor.id:
            raise DomainValidationError("you cannot delete your own account")
        await self._users.delete(user_id)
        await self._audit(actor.id, "user.delete", user_id, {"email": target.email})

    # ------------------------------------------------------------------ #
    # Pre-provisioned elevation list
    # ------------------------------------------------------------------ #
    async def list_role_assignments(self, page: PageRequest) -> Page[RoleAssignment]:
        return await self._assignments.list(page)

    async def create_role_assignment(
        self, *, email: str, role: UserRole, actor: User
    ) -> RoleAssignment:
        """Pre-provision ``role`` for ``email``, to take effect at account creation."""
        if role not in ELEVATED_ROLES:
            raise DomainValidationError(
                f"{role.value} cannot be pre-provisioned: every org-domain account "
                "already receives EMPLOYEE by default"
            )
        if role.level > actor.role.level:
            raise PermissionDeniedError("cannot assign a role above your own")

        # Admission first: an address that could never hold an account must not
        # be allowed to sit on the elevation list either.
        normalized = assert_org_email(email, self._allowed_domains, self._allowed_exceptions)

        if await self._users.get_by_email(normalized) is not None:
            raise LiveUserExistsError(normalized)
        if await self._assignments.get_by_email(normalized) is not None:
            raise DuplicateEntityError("RoleAssignment", "email", normalized)

        created = await self._assignments.add(
            RoleAssignment(email=normalized, role=role, assigned_by=actor.id)
        )
        await self._audit(
            actor.id,
            "role_assignment.create",
            created.id,
            {"email": normalized, "role": role.value},
            entity_type="RoleAssignment",
        )
        return created

    async def revoke_role_assignment(self, assignment_id: UUID, *, actor: User) -> None:
        """Delete an unconsumed assignment.

        A consumed row is history — the account it created already exists and
        its role now lives on the User record, so deleting the row would
        neither undo anything nor be honest about what happened.
        """
        assignment = await self._assignments.get(assignment_id)
        if assignment is None:
            raise EntityNotFoundError("RoleAssignment", assignment_id)
        if assignment.is_consumed:
            raise AssignmentConsumedError(str(assignment_id))
        if assignment.role.level > actor.role.level:
            raise PermissionDeniedError("cannot revoke an assignment above your own role")

        await self._assignments.delete(assignment_id)
        await self._audit(
            actor.id,
            "role_assignment.revoke",
            assignment_id,
            {"email": assignment.email, "role": assignment.role.value},
            entity_type="RoleAssignment",
        )

    async def list_audit_logs(
        self,
        page: PageRequest,
        *,
        actor_id: UUID | None = None,
        entity_type: str | None = None,
        action: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Page[AuditLog]:
        return await self._audits.list(
            page,
            actor_id=actor_id,
            entity_type=entity_type,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _require_authority_over(actor: User, target: User) -> None:
        if target.role.level > actor.role.level:
            raise PermissionDeniedError("cannot modify a more privileged user")

    async def _revoke_sessions(self, user_id: UUID) -> None:
        for session in await self._sessions.list_for_user(user_id):
            if session.is_active:
                session.revoke()
                await self._sessions.update(session)

    async def _audit(
        self,
        actor_id: UUID,
        action: str,
        entity_id: UUID,
        diff: dict[str, Any],
        *,
        entity_type: str = "User",
    ) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
                actor_id=actor_id,
                diff=diff,
            )
        )
