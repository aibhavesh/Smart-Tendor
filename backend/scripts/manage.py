"""Role and account administration from the command line.

Every subcommand calls the same application service the HTTP endpoint calls, so
the domain rules and the audit trail are identical to doing it in the browser.
Nothing here writes SQL.

    cd backend

    # Once, on an empty database. Refuses if a SUPER_ADMIN already exists.
    python scripts/manage.py bootstrap --email founder@example.com --password "..."

    python scripts/manage.py list-users
    python scripts/manage.py set-role someone@example.com --role MANAGER --actor you@example.com
    python scripts/manage.py pre-provision new@example.com --role ADMIN --actor you@example.com
    python scripts/manage.py deactivate someone@example.com --actor you@example.com --yes

Why this exists
---------------
``PATCH /admin/users/{id}/role`` has been available and tested for a long time,
but for a long time no screen called it either. The only routes to change a role
were hand-written SQL against the database, which bypasses the authority rules
and writes no audit entry. This tool is the non-SQL route for anyone without a
browser session.

Who is allowed to do what
------------------------
``bootstrap`` is the sole exception to the named-actor rule, because it *creates*
the first administrator and so has nobody to name. It uses a system actor
(``actor_id`` NULL), the same convention as bootstrap migration ``d4a1e9c5b872``,
and it refuses outright once any SUPER_ADMIN exists so it can never be used to
mint extra super admins.

Every other subcommand requires ``--actor``, resolved to a real account, and is
subject to the same inherited rules as the UI:

  - cannot assign a role above the actor's own level
  - cannot modify an account more privileged than the actor's
  - ``deactivate`` refuses the actor's own account and revokes every session

Exit codes: 0 success, 1 refused by a domain rule, 2 bad usage.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from tender_intel.core.config import get_settings
from tender_intel.domain.entities import AuditLog, User
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.exceptions import DomainError, EntityNotFoundError, PermissionDeniedError
from tender_intel.domain.value_objects.pagination import PageRequest
from tender_intel.infrastructure.db.orm import UserModel
from tender_intel.infrastructure.db.session import create_engine, create_session_factory
from tender_intel.infrastructure.operator import OperatorServices, build_operator_services

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

COMMANDS = (
    "bootstrap",
    "list-users",
    "set-role",
    "pre-provision",
    "revoke-pre-provision",
    "deactivate",
)


def _fail(message: str, code: int = EXIT_REFUSED) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
async def _resolve_actor(services: OperatorServices, email: str) -> User | None:
    """The account named by ``--actor``, or ``None`` if there is no such account.

    A deactivated account is refused here rather than returned, so every caller
    gets the same behaviour without repeating the check.
    """
    user = await services.admin.users.get_by_email(email.strip().lower())
    if user is None:
        return None
    if not user.is_active:
        raise PermissionDeniedError(
            f"{email} is deactivated and cannot act. Reactivate the account first."
        )
    return user


async def _lookup_user(services: OperatorServices, email: str) -> User | None:
    return await services.admin.users.get_by_email(email.strip().lower())


async def _count_super_admins(services: OperatorServices) -> int:
    rows = (
        (
            await services.session.execute(
                select(UserModel).where(UserModel.role == UserRole.SUPER_ADMIN.value)
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


def _print_user(user: User) -> None:
    flag = "" if user.is_active else "  (deactivated)"
    print(f"  {user.email:<44} {user.role.value:<12} {user.full_name}{flag}")


# --------------------------------------------------------------------------- #
# Subcommands
#
# Each receives already-built services rather than opening its own connection, so
# a command is exercisable against one injected database. ``main`` is the only
# place that owns an engine.
# --------------------------------------------------------------------------- #
async def cmd_bootstrap(services: OperatorServices, args: argparse.Namespace) -> int:
    """Create the first SUPER_ADMIN. Refuses if one already exists."""
    if await _count_super_admins(services) > 0:
        await services.rollback()
        return _fail(
            "a SUPER_ADMIN already exists. This command is only for the first "
            "administrator; use `set-role` (which needs a named --actor) instead."
        )

    email = args.email.strip().lower()
    existing = await _lookup_user(services, email)
    if existing is not None:
        # The account exists, so the elevation list no longer governs it.
        # Promoting it here would be a role change and needs a named actor.
        await services.rollback()
        return _fail(
            f"{email} already has an account (role {existing.role.value}). "
            "Promote it with `set-role` and a named --actor, so the change is "
            "attributable to a person."
        )

    try:
        # Deliberately goes through register(), the same path as
        # POST /auth/register: same admission gate, same password hashing.
        await services.auth.register(
            email=email,
            password=args.password,
            full_name=args.full_name,
            ip=None,
            user_agent="manage.py bootstrap",
        )
    except DomainError as exc:
        await services.rollback()
        return _fail(str(exc))

    user = await _lookup_user(services, email)
    if user is None:  # pragma: no cover - register() returned without a row
        await services.rollback()
        return _fail("the account was not created")

    user.role = UserRole.SUPER_ADMIN
    user = await services.admin.users.update(user)
    # System actor: there is no administrator yet to attribute this to. This
    # mirrors migration d4a1e9c5b872, which writes assigned_by = NULL.
    await services.admin.audits.add(
        AuditLog(
            action="user.bootstrap_super_admin",
            entity_type="User",
            entity_id=str(user.id),
            actor_id=None,
            diff={"role": {"before": UserRole.EMPLOYEE.value, "after": user.role.value}},
            user_agent="manage.py bootstrap",
        )
    )
    await services.commit()

    print(f"Created {user.email} as {user.role.value}.")
    print("This is the only account this command will ever create.")
    return EXIT_OK


async def cmd_list_users(services: OperatorServices, args: argparse.Namespace) -> int:
    page = await services.admin.list_users(PageRequest(limit=args.limit, offset=0))
    if not page.items:
        print("No accounts yet.")
        return EXIT_OK
    print(f"{page.total} account(s):")
    for user in sorted(page.items, key=lambda u: (-u.role.level, u.email)):
        _print_user(user)
    return EXIT_OK


async def cmd_set_role(services: OperatorServices, args: argparse.Namespace) -> int:
    try:
        actor = await _resolve_actor(services, args.actor)
        if actor is None:
            await services.rollback()
            return _fail(f"no account for {args.actor} to act as")

        target = await _lookup_user(services, args.email)
        if target is None:
            await services.rollback()
            return _fail(f"no account for {args.email}. Use `pre-provision` instead.")

        before = target.role.value
        # change_role enforces: not above your own level, and not someone more
        # privileged than you. It writes the audit diff itself.
        updated = await services.admin.change_role(target.id, args.role, actor=actor)
        await services.commit()
    except DomainError as exc:
        await services.rollback()
        return _fail(str(exc))

    if before == updated.role.value:
        print(f"{updated.email} is already {updated.role.value}.")
    else:
        print(f"{updated.email}: {before} -> {updated.role.value}")
    return EXIT_OK


async def cmd_pre_provision(services: OperatorServices, args: argparse.Namespace) -> int:
    try:
        actor = await _resolve_actor(services, args.actor)
        if actor is None:
            await services.rollback()
            return _fail(f"no account for {args.actor} to act as")

        created = await services.admin.create_role_assignment(
            email=args.email.strip().lower(),
            role=args.role,
            actor=actor,
        )
        await services.commit()
    except DomainError as exc:
        await services.rollback()
        return _fail(str(exc))

    print(f"{created.email} will be born {created.role.value} on first sign-in.")
    print("That row is read once, at account creation, and never again.")
    return EXIT_OK


async def cmd_revoke_pre_provision(services: OperatorServices, args: argparse.Namespace) -> int:
    try:
        actor = await _resolve_actor(services, args.actor)
        if actor is None:
            await services.rollback()
            return _fail(f"no account for {args.actor} to act as")

        page = await services.admin.list_role_assignments(PageRequest(limit=200))
        match = next((r for r in page.items if r.email.lower() == args.email.strip().lower()), None)
        if match is None:
            await services.rollback()
            return _fail(f"no pre-provisioned role for {args.email}")

        await services.admin.revoke_role_assignment(match.id, actor=actor)
        await services.commit()
    except DomainError as exc:
        await services.rollback()
        return _fail(str(exc))

    print(f"Removed the pre-provisioned role for {args.email}.")
    return EXIT_OK


async def cmd_deactivate(services: OperatorServices, args: argparse.Namespace) -> int:
    try:
        actor = await _resolve_actor(services, args.actor)
        if actor is None:
            await services.rollback()
            return _fail(f"no account for {args.actor} to act as")

        target = await _lookup_user(services, args.email)
        if target is None:
            await services.rollback()
            return _fail(f"no account for {args.email}")

        # set_active enforces "cannot deactivate yourself" and revokes every
        # active session belonging to that account.
        await services.admin.set_active(target.id, False, actor=actor)
        await services.commit()
    except DomainError as exc:
        await services.rollback()
        return _fail(str(exc))

    print(f"{args.email} deactivated. Their active sessions were revoked.")
    return EXIT_OK


HANDLERS = {
    "bootstrap": cmd_bootstrap,
    "list-users": cmd_list_users,
    "set-role": cmd_set_role,
    "pre-provision": cmd_pre_provision,
    "revoke-pre-provision": cmd_revoke_pre_provision,
    "deactivate": cmd_deactivate,
}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Administer accounts and roles without writing SQL.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    role_choices = [r.value for r in UserRole]

    def add_actor(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--actor",
            required=True,
            help="An existing account to record as the actor.",
        )

    p = sub.add_parser("bootstrap", help="Create the FIRST SUPER_ADMIN. Refuses if one exists.")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--full-name", default="Administrator")

    p = sub.add_parser("list-users", help="List every account and its role.")
    p.add_argument("--limit", type=int, default=200)

    p = sub.add_parser("set-role", help="Change an existing account's role.")
    p.add_argument("email")
    p.add_argument("--role", required=True, choices=role_choices)
    add_actor(p)

    p = sub.add_parser("pre-provision", help="Grant a role to somebody who has NOT signed in.")
    p.add_argument("email")
    p.add_argument("--role", required=True, choices=role_choices)
    add_actor(p)

    p = sub.add_parser("revoke-pre-provision", help="Remove an unconsumed pre-provisioned role.")
    p.add_argument("email")
    add_actor(p)

    p = sub.add_parser("deactivate", help="Deactivate an account and revoke its sessions.")
    p.add_argument("email")
    add_actor(p)
    p.add_argument(
        "--yes",
        action="store_true",
        help="Required. Deactivation ends that person's access immediately.",
    )

    return parser


async def _dispatch(argv: list[str]) -> int:
    """Parse, open one session, and run the selected command over it."""
    args = build_parser().parse_args(argv)

    if args.command == "deactivate" and not args.yes:
        # Checked before any database work: this is a usage error, not a refusal.
        return _fail(
            f"deactivating {args.email} ends their access immediately. Pass --yes to confirm.",
            EXIT_USAGE,
        )

    if args.command in {"set-role", "pre-provision"}:
        args.role = UserRole(args.role)

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            services = build_operator_services(session, settings)
            return await HANDLERS[args.command](services, args)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(_dispatch(list(sys.argv[1:] if argv is None else argv)))
    except EntityNotFoundError as exc:
        return _fail(str(exc))
    except DomainError as exc:
        return _fail(str(exc))
    except KeyboardInterrupt:  # pragma: no cover
        return _fail("interrupted", EXIT_USAGE)


if __name__ == "__main__":
    raise SystemExit(main())
