"""Authentication & account lifecycle use cases (FR-501..FR-508).

Two independent sign-in methods share one architecture: Google (a verified ID
token) and manual email/password. Either one may create an account, and both
are subject to the same two gates, in order:

1. **Admission** — :func:`assert_org_email` rejects any address outside the
   configured organisation domains, before any row is written. A short list of
   individually named addresses may be excepted for people who need access
   without being on one. This applies to :meth:`google_login` *and*
   :meth:`register` alike — manual sign-up does not bypass it.
2. **Elevation** — a RoleAssignment row for that normalised address decides the
   role the account is born with; without one the account is EMPLOYEE.

Elevation is evaluated at creation only. A returning user's role is read from
their User row and never re-derived, so a later assignment cannot silently
change a live account.

Manual sign-up never creates a second account for an address that already has
one, Google or password (see :meth:`register`). Google remains entirely
optional: unconfigured or unused, :meth:`register`/:meth:`login` work on their
own, and vice versa for an installation with no manual accounts.

Emits an audit-log entry on every state-changing action (cross-cutting
requirement).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from tender_intel.application.dto.auth import TokenPair
from tender_intel.core.config import Settings
from tender_intel.domain.entities import AuditLog, User, UserSession
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.exceptions import (
    AuthenticationError,
    DuplicateEntityError,
    EntityNotFoundError,
    ForbiddenDomainError,
    InactiveUserError,
    InvalidTokenError,
)
from tender_intel.domain.interfaces.providers import GoogleIdentity, GoogleTokenVerifier
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    RoleAssignmentRepository,
    UserRepository,
    UserSessionRepository,
)
from tender_intel.domain.services.email_domain import (
    assert_org_email,
    is_excepted,
    normalize_email,
)
from tender_intel.infrastructure.security.passwords import hash_password, verify_password
from tender_intel.infrastructure.security.tokens import TokenService, TokenType, hash_refresh_token


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: UserSessionRepository,
        assignments: RoleAssignmentRepository,
        audits: AuditLogRepository,
        tokens: TokenService,
        google: GoogleTokenVerifier,
        settings: Settings,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._assignments = assignments
        self._audits = audits
        self._tokens = tokens
        self._google = google
        self._allowed_domains = settings.allowed_email_domains
        self._allowed_exceptions = settings.allowed_email_exceptions
        self._access_ttl_seconds = settings.access_token_ttl_minutes * 60

    # ------------------------------------------------------------------ #
    # Google sign-in — optional; not the only way an account is created
    # ------------------------------------------------------------------ #
    async def google_login(
        self, *, id_token: str, ip: str | None, user_agent: str | None
    ) -> TokenPair:
        identity = await self._google.verify(id_token)
        normalized = self._admit_google(identity)

        user = await self._users.get_by_google_sub(identity.subject)
        if user is None:
            existing = await self._users.get_by_email(normalized)
            if existing is not None:
                existing.google_sub = identity.subject  # link Google to the account
                user = await self._users.update(existing)
            else:
                user = await self._create_account(
                    normalized, identity.full_name, google_sub=identity.subject
                )

        self._require_active(user)
        user.last_login_at = datetime.now(UTC)
        await self._users.update(user)
        pair = await self._issue_pair(user, ip, user_agent)
        await self._audit(user.id, "user.google_login", "User", user.id)
        return pair

    def _admit_google(self, identity: GoogleIdentity) -> str:
        """Apply the admission gate, returning the normalised address.

        When Google asserts a hosted domain we check that too: ``hd`` is a
        claim Google vouches for, so a mismatch means the account is not on the
        organisation's Workspace even if the address happens to read like it.
        Both checks must pass; ``hd`` does not substitute for the address check.

        An individually excepted address short-circuits both. It has to: such a
        person is by definition not on an organisation domain, so their ``hd``
        would name their own employer and the check above would refuse them
        before the exception was ever consulted.
        """
        normalized = normalize_email(identity.email)
        if is_excepted(normalized, self._allowed_exceptions):
            return normalized

        if identity.hosted_domain is not None and identity.hosted_domain not in set(
            self._allowed_domains
        ):
            raise ForbiddenDomainError(
                f"Google hosted domain {identity.hosted_domain!r} is not an allowed "
                "organisation domain"
            )
        return assert_org_email(identity.email, self._allowed_domains)

    # ------------------------------------------------------------------ #
    # Manual sign-in — optional, and equally subject to the admission gate
    # ------------------------------------------------------------------ #
    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        ip: str | None,
        user_agent: str | None,
    ) -> TokenPair:
        """Create an account with an email/password credential and sign it in.

        Subject to the same admission gate as Google sign-in
        (:func:`assert_org_email`), so manual sign-up cannot admit an address
        Google sign-in would refuse. Refuses a duplicate email outright rather
        than attaching a password to an existing (possibly Google-only)
        account — linking a credential onto someone else's account is not a
        decision this endpoint should make silently.
        """
        normalized = assert_org_email(email, self._allowed_domains, self._allowed_exceptions)
        if await self._users.get_by_email(normalized) is not None:
            raise DuplicateEntityError("User", "email", normalized)

        user = await self._create_account(
            normalized, full_name.strip(), hashed_password=hash_password(password)
        )
        user.last_login_at = datetime.now(UTC)
        user = await self._users.update(user)
        pair = await self._issue_pair(user, ip, user_agent)
        await self._audit(user.id, "user.register", "User", user.id)
        return pair

    async def login(
        self, *, email: str, password: str, ip: str | None, user_agent: str | None
    ) -> TokenPair:
        """Verify an email/password credential and sign the account in.

        One generic failure (:class:`AuthenticationError`) covers "no such
        user", "wrong password" and "this account has no password (it is
        Google-only)" alike — distinguishing them to the caller would let an
        attacker enumerate registered addresses or discover which sign-in
        method an account uses.
        """
        normalized = normalize_email(email)
        user = await self._users.get_by_email(normalized)
        if (
            user is None
            or user.hashed_password is None
            or not verify_password(password, user.hashed_password)
        ):
            raise AuthenticationError("invalid email or password")

        self._require_active(user)
        user.last_login_at = datetime.now(UTC)
        await self._users.update(user)
        pair = await self._issue_pair(user, ip, user_agent)
        await self._audit(user.id, "user.login", "User", user.id)
        return pair

    # ------------------------------------------------------------------ #
    # Account creation — shared by every sign-in method
    # ------------------------------------------------------------------ #
    async def _create_account(
        self,
        normalized: str,
        full_name: str,
        *,
        google_sub: str | None = None,
        hashed_password: str | None = None,
    ) -> User:
        """Create the account, honouring a pre-provisioned elevation if one exists."""
        assignment = await self._assignments.get_by_email(normalized)
        role = assignment.role if assignment is not None else UserRole.EMPLOYEE
        created = await self._users.add(
            User(
                email=normalized,
                full_name=full_name,
                role=role,
                google_sub=google_sub,
                hashed_password=hashed_password,
            )
        )
        if assignment is not None:
            assignment.consume(created.id)
            await self._assignments.update(assignment)
        await self._audit(
            created.id,
            "user.created",
            "User",
            created.id,
            {
                "email": normalized,
                "role": role.value,
                "role_assignment_id": str(assignment.id) if assignment else None,
            },
        )
        return created

    # ------------------------------------------------------------------ #
    # Refresh & logout
    # ------------------------------------------------------------------ #
    async def refresh(
        self, *, refresh_token: str, ip: str | None, user_agent: str | None
    ) -> TokenPair:
        self._tokens.decode(refresh_token, TokenType.REFRESH)  # signature/type/expiry
        session = await self._sessions.get_by_token_hash(hash_refresh_token(refresh_token))
        if session is None or not session.is_active:
            raise InvalidTokenError("refresh token is not active")

        user = await self._users.get(session.user_id)
        if user is None:
            raise InvalidTokenError("user no longer exists")
        self._require_active(user)

        # Rotate: revoke the presented session, issue a fresh pair.
        session.revoke()
        await self._sessions.update(session)
        return await self._issue_pair(user, ip, user_agent)

    async def logout(self, *, refresh_token: str) -> None:
        session = await self._sessions.get_by_token_hash(hash_refresh_token(refresh_token))
        if session is not None and session.is_active:
            session.revoke()
            await self._sessions.update(session)
            await self._audit(session.user_id, "user.logout", "UserSession", session.id)

    # ------------------------------------------------------------------ #
    # Deactivation
    # ------------------------------------------------------------------ #
    async def deactivate(self, *, user_id: UUID, actor_id: UUID) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise EntityNotFoundError("User", user_id)
        user.is_active = False
        updated = await self._users.update(user)
        await self._revoke_all_sessions(user_id)
        await self._audit(
            actor_id,
            "user.deactivate",
            "User",
            user_id,
            {"is_active": {"before": True, "after": False}},
        )
        return updated

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _require_active(user: User) -> None:
        if not user.is_active:
            raise InactiveUserError("account is deactivated")

    async def _issue_pair(self, user: User, ip: str | None, user_agent: str | None) -> TokenPair:
        access = self._tokens.create_access_token(user)
        refresh = self._tokens.create_refresh_token(user)
        await self._sessions.add(
            UserSession(
                user_id=user.id,
                refresh_token_hash=hash_refresh_token(refresh.token),
                expires_at=refresh.expires_at,
                ip_address=ip,
                user_agent=user_agent,
            )
        )
        return TokenPair(
            access_token=access.token,
            refresh_token=refresh.token,
            expires_in=self._access_ttl_seconds,
        )

    async def _revoke_all_sessions(self, user_id: UUID) -> None:
        for session in await self._sessions.list_for_user(user_id):
            if session.is_active:
                session.revoke()
                await self._sessions.update(session)

    async def _audit(
        self,
        actor_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID,
        diff: dict[str, Any] | None = None,
    ) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
                actor_id=actor_id,
                diff=diff or {},
            )
        )
