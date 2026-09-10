"""Seed a default email/password account for local sign-in.

Run this once against your local database when you want a ready-made account
to log in with immediately, instead of using the /register page yourself:

    cd backend
    python scripts/create_default_user.py
    python scripts/create_default_user.py --email you@yourcompany.com --password "Something8+"

It does not start the server, add a dependency, or touch any .env file — it
opens the same database the app uses (``DATABASE_URL`` from your existing
settings) and calls the exact same ``AuthService.register()`` that
``POST /auth/register`` calls, so the created account is subject to the same
organisation-domain check, the same duplicate-email check, and the same
password hashing as a real sign-up. If ``BOOTSTRAP_SUPER_ADMIN_EMAIL`` is set
in your .env and you seed that address, the account is created as
SUPER_ADMIN; otherwise it is born EMPLOYEE (or whatever role a pre-provisioned
role assignment already grants that email), same as any other sign-up.

Safe to re-run: if the email already has an account, the script says so and
exits without changing anything (register() itself rejects the duplicate).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from tender_intel.application.services.auth_service import AuthService
from tender_intel.core.config import get_settings
from tender_intel.domain.exceptions import DuplicateEntityError, ForbiddenDomainError
from tender_intel.infrastructure.db.session import create_engine, create_session_factory
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

DEFAULT_EMAIL = "testuser@maheshwaricomputers.com"
DEFAULT_PASSWORD = "TestUser@123"
DEFAULT_NAME = "Test User"


async def _create(email: str, password: str, full_name: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    async with factory() as session:
        auth_service = AuthService(
            users=SqlAlchemyUserRepository(session),
            sessions=SqlAlchemyUserSessionRepository(session),
            assignments=SqlAlchemyRoleAssignmentRepository(session),
            audits=SqlAlchemyAuditLogRepository(session),
            tokens=TokenService(settings),
            google=GoogleTokenVerifierImpl(settings.google_client_id),
            settings=settings,
        )
        try:
            await auth_service.register(
                email=email,
                password=password,
                full_name=full_name,
                ip=None,
                user_agent="create_default_user.py",
            )
            await session.commit()
        except DuplicateEntityError:
            await session.rollback()
            print(f"An account for {email} already exists — nothing changed.")
            print("Sign in with it at /login using whatever password it was created with.")
            return
        except ForbiddenDomainError as exc:
            await session.rollback()
            print(f"Could not create {email}: {exc}", file=sys.stderr)
            print(
                "That address isn't on this deployment's allowed organisation domain "
                "(ALLOWED_EMAIL_DOMAINS / ALLOWED_EMAIL_EXCEPTIONS in your .env). "
                "Pass --email with an address on that domain instead.",
                file=sys.stderr,
            )
            sys.exit(1)

    await engine.dispose()
    print(f"Created {email} — sign in at /login with:")
    print(f"  email:    {email}")
    print(f"  password: {password}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=DEFAULT_EMAIL, help=f"default: {DEFAULT_EMAIL}")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help=f"default: {DEFAULT_PASSWORD}")
    parser.add_argument("--full-name", default=DEFAULT_NAME, help=f"default: {DEFAULT_NAME}")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_create(args.email, args.password, args.full_name))


if __name__ == "__main__":
    main()
