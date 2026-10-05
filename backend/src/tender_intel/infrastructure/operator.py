"""Construct the real application services against an explicit session.

Both operator scripts — ``create_default_user.py`` and ``manage.py`` — need to
build the *same* services the HTTP layer builds, so that a command-line change is
subject to exactly the domain rules and produces exactly the audit entries that
the equivalent request would. Sharing one definition is what guarantees that: a
script cannot drift from the API because it is not repeating the wiring.

This lives in ``tender_intel`` rather than in ``scripts/`` because it is
application composition, not a script concern, and because importing it from
outside ``scripts/`` is legitimate.

The FastAPI dependency providers in ``api/dependencies/services.py`` remain the
composition root for the running service. This is the operator-side equivalent
and deliberately mirrors it; a test asserts the two construct the same service
types so they cannot diverge unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.application.services.admin_service import AdminService
from tender_intel.application.services.auth_service import AuthService
from tender_intel.core.config import Settings
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.role_assignment_repo import (
    SqlAlchemyRoleAssignmentRepository,
)
from tender_intel.infrastructure.repositories.user_repo import (
    SqlAlchemyUserRepository,
    SqlAlchemyUserSessionRepository,
)
from tender_intel.infrastructure.security.google import GoogleTokenVerifierImpl
from tender_intel.infrastructure.security.tokens import TokenService


@dataclass(frozen=True, slots=True)
class OperatorServices:
    """The services an operator script needs, bound to one session.

    Frozen on purpose: a script should not be able to swap a repository out from
    under a service and quietly bypass a rule.
    """

    session: AsyncSession
    auth: AuthService
    admin: AdminService
    settings: Settings

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


def build_operator_services(session: AsyncSession, settings: Settings) -> OperatorServices:
    """Build the auth and admin services over ``session``, as the API would."""
    users = SqlAlchemyUserRepository(session)
    sessions = SqlAlchemyUserSessionRepository(session)
    assignments = SqlAlchemyRoleAssignmentRepository(session)
    audits = SqlAlchemyAuditLogRepository(session)
    tokens = TokenService(settings)
    google = GoogleTokenVerifierImpl(settings.google_client_id)

    return OperatorServices(
        session=session,
        auth=AuthService(
            users=users,
            sessions=sessions,
            assignments=assignments,
            audits=audits,
            tokens=tokens,
            google=google,
            settings=settings,
        ),
        admin=AdminService(
            users=users,
            sessions=sessions,
            assignments=assignments,
            audits=audits,
            settings=settings,
        ),
        settings=settings,
    )
