"""The operator CLI's command handlers, driven against in-memory SQLite.

These exist to prove the CLI *inherits* the authority rules rather than bypassing
them. A tool that could promote anyone to SUPER_ADMIN, or edit a SUPER_ADMIN,
would be worse than the SQL it replaced: unaudited superuser access behind a
friendly command line.

Handlers are called directly rather than through ``main`` because the fixtures
hold an in-memory SQLite database on a ``StaticPool`` — one shared connection that
a second engine cannot open. Going through ``main`` would build a fresh engine
from ``DATABASE_URL`` and reach a different database, so the tests would pass
while proving nothing. ``main``'s own behaviour is covered by the argv-level
tests at the bottom.
"""

from __future__ import annotations

import argparse
import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from tender_intel.core.config import Environment, Settings
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.value_objects.pagination import PageRequest
from tests.integration.helpers import seed_user
from tests.integration.manage_loader import load_manage

ORG = "maheshwaricomputers.com"

manage = load_manage()


@pytest.fixture
def services(app_db):
    """The real services over the fixture's own session — what the CLI builds."""
    from tender_intel.infrastructure.operator import build_operator_services

    async def _services():
        settings = Settings(
            environment=Environment.CI,
            jwt_secret="test-secret-value-that-is-long-enough-1234",
            allowed_email_domains=[ORG],
        )
        async with app_db.state.test_session_factory() as session:
            return build_operator_services(session, settings)

    return _services


async def _run(services, command, **kwargs) -> tuple[int, str]:
    """Invoke a handler the way the dispatcher does, capturing its output."""
    args = argparse.Namespace(command=command, **kwargs)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = await manage.HANDLERS[command](services, args)
    return code, out.getvalue() + err.getvalue()


async def _bootstrap(services, email: str) -> int:
    code, _ = await _run(
        services,
        "bootstrap",
        email=email,
        password="correct-horse-battery",
        full_name="Founder",
    )
    return code


async def _bootstrap_output(services, email: str) -> tuple[int, str]:
    return await _run(
        services,
        "bootstrap",
        email=email,
        password="correct-horse-battery",
        full_name="Founder",
    )


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #
async def test_bootstrap_creates_the_first_super_admin(services, app_db):
    from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository

    svc = await services()
    code, output = await _bootstrap_output(svc, f"founder@{ORG}")
    assert code == 0, output
    assert "SUPER_ADMIN" in output

    async with app_db.state.test_session_factory() as session:
        created = await SqlAlchemyUserRepository(session).get_by_email(f"founder@{ORG}")
    assert created is not None
    assert created.role is UserRole.SUPER_ADMIN


async def test_bootstrap_refuses_when_a_super_admin_exists(services, app_db):
    """The whole point: this command must never mint a second super admin."""
    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    svc = await services()
    code, output = await _bootstrap_output(svc, f"second@{ORG}")
    assert code == 1
    assert "SUPER_ADMIN already exists" in output

    # And it really did not create the account.
    from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository

    async with app_db.state.test_session_factory() as session:
        assert await SqlAlchemyUserRepository(session).get_by_email(f"second@{ORG}") is None


async def test_bootstrap_refuses_for_an_address_that_already_has_an_account(services, app_db):
    """An existing account is a role change and needs a named actor to attribute it."""
    await seed_user(app_db, email=f"here@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()
    code, output = await _bootstrap_output(svc, f"here@{ORG}")
    assert code == 1
    assert "already has an account" in output


async def test_bootstrap_refuses_an_address_off_the_allowed_domain(services, app_db):
    svc = await services()
    assert await _bootstrap(svc, "someone@elsewhere.invalid") == 1


async def test_bootstrap_writes_a_system_actor_audit_entry(services, app_db):
    """actor_id is None: there is no administrator yet to attribute it to."""
    from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository

    svc = await services()
    assert await _bootstrap(svc, f"founder@{ORG}") == 0

    async with app_db.state.test_session_factory() as session:
        entries = [
            e
            for e in (await SqlAlchemyAuditLogRepository(session).list(PageRequest(limit=50))).items
            if e.action == "user.bootstrap_super_admin"
        ]
    assert len(entries) == 1
    assert entries[0].actor_id is None
    assert entries[0].diff == {"role": {"before": "EMPLOYEE", "after": "SUPER_ADMIN"}}


# --------------------------------------------------------------------------- #
# Authority rules — the reason this file exists
# --------------------------------------------------------------------------- #
async def test_an_admin_cannot_grant_super_admin(services, app_db):
    await seed_user(app_db, email=f"admin@{ORG}", role=UserRole.ADMIN)
    await seed_user(app_db, email=f"staff@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()
    code, output = await _run(
        svc,
        "set-role",
        email=f"staff@{ORG}",
        role=UserRole.SUPER_ADMIN,
        actor=f"admin@{ORG}",
    )
    assert code == 1
    assert "above your own" in output


async def test_an_admin_cannot_modify_a_super_admin(services, app_db):
    await seed_user(app_db, email=f"admin@{ORG}", role=UserRole.ADMIN)
    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    svc = await services()
    code, output = await _run(
        svc,
        "set-role",
        email=f"boss@{ORG}",
        role=UserRole.EMPLOYEE,
        actor=f"admin@{ORG}",
    )
    assert code == 1
    assert "more privileged" in output


async def test_an_admin_cannot_edit_their_own_account(services, app_db):
    await seed_user(app_db, email=f"admin@{ORG}", role=UserRole.ADMIN)
    svc = await services()
    code, _ = await _run(
        svc,
        "set-role",
        email=f"admin@{ORG}",
        role=UserRole.SUPER_ADMIN,
        actor=f"admin@{ORG}",
    )
    assert code == 1


async def test_an_employee_actor_cannot_promote_anyone(services, app_db):
    await seed_user(app_db, email=f"staff@{ORG}", role=UserRole.EMPLOYEE)
    await seed_user(app_db, email=f"other@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()
    code, _ = await _run(
        svc,
        "set-role",
        email=f"other@{ORG}",
        role=UserRole.MANAGER,
        actor=f"staff@{ORG}",
    )
    assert code == 1


async def test_an_unknown_actor_is_refused(services, app_db):
    await seed_user(app_db, email=f"staff@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()
    code, output = await _run(
        svc,
        "set-role",
        email=f"staff@{ORG}",
        role=UserRole.MANAGER,
        actor=f"nobody@{ORG}",
    )
    assert code == 1
    assert "no account" in output


async def test_a_deactivated_actor_cannot_act(services, app_db):
    await seed_user(app_db, email=f"ex@{ORG}", role=UserRole.ADMIN, is_active=False)
    await seed_user(app_db, email=f"staff@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()
    code, output = await _run(
        svc,
        "set-role",
        email=f"staff@{ORG}",
        role=UserRole.MANAGER,
        actor=f"ex@{ORG}",
    )
    assert code == 1
    assert "deactivated" in output


# --------------------------------------------------------------------------- #
# The happy paths
# --------------------------------------------------------------------------- #
async def test_a_super_admin_can_promote_and_it_is_audited(services, app_db):
    from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
    from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository

    actor = await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    await seed_user(app_db, email=f"staff@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()

    code, output = await _run(
        svc,
        "set-role",
        email=f"staff@{ORG}",
        role=UserRole.MANAGER,
        actor=f"boss@{ORG}",
    )
    assert code == 0, output
    assert "EMPLOYEE -> MANAGER" in output

    async with app_db.state.test_session_factory() as session:
        updated = await SqlAlchemyUserRepository(session).get_by_email(f"staff@{ORG}")
        assert updated.role is UserRole.MANAGER

        entries = [
            e
            for e in (await SqlAlchemyAuditLogRepository(session).list(PageRequest(limit=50))).items
            if e.action == "user.role_change"
        ]
    assert entries, "no user.role_change entry was written"
    assert entries[0].diff == {"role": {"before": "EMPLOYEE", "after": "MANAGER"}}
    assert entries[0].actor_id == actor.id


async def test_a_manager_can_promote_someone_below_them(services, app_db):
    """MANAGER (30) may act on EMPLOYEE (20) — the hierarchy is inclusive."""
    from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository

    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.MANAGER)
    await seed_user(app_db, email=f"staff@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()

    code, output = await _run(
        svc,
        "set-role",
        email=f"staff@{ORG}",
        role=UserRole.MANAGER,
        actor=f"boss@{ORG}",
    )
    assert code == 0, output

    async with app_db.state.test_session_factory() as session:
        updated = await SqlAlchemyUserRepository(session).get_by_email(f"staff@{ORG}")
    assert updated.role is UserRole.MANAGER


async def test_pre_provision_grants_a_role_for_a_future_sign_in(services, app_db):
    from tender_intel.infrastructure.repositories.role_assignment_repo import (
        SqlAlchemyRoleAssignmentRepository,
    )

    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    svc = await services()

    code, output = await _run(
        svc,
        "pre-provision",
        email=f"newjoiner@{ORG}",
        role=UserRole.ADMIN,
        actor=f"boss@{ORG}",
    )
    assert code == 0, output
    assert "born ADMIN" in output

    async with app_db.state.test_session_factory() as session:
        row = await SqlAlchemyRoleAssignmentRepository(session).get_by_email(f"newjoiner@{ORG}")
    assert row is not None
    assert row.role is UserRole.ADMIN
    assert row.is_consumed is False


async def test_pre_provision_refuses_an_address_that_already_has_an_account(services, app_db):
    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    await seed_user(app_db, email=f"here@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()
    code, _ = await _run(
        svc,
        "pre-provision",
        email=f"here@{ORG}",
        role=UserRole.ADMIN,
        actor=f"boss@{ORG}",
    )
    assert code == 1


async def test_pre_provision_refuses_the_default_role(services, app_db):
    """An EMPLOYEE row would carry no information — the floor is automatic."""
    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    svc = await services()
    code, _ = await _run(
        svc,
        "pre-provision",
        email=f"newjoiner@{ORG}",
        role=UserRole.EMPLOYEE,
        actor=f"boss@{ORG}",
    )
    assert code == 1


async def test_deactivate_revokes_active_sessions(services, app_db):
    from tender_intel.infrastructure.repositories.user_repo import SqlAlchemyUserRepository

    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    target = await seed_user(app_db, email=f"staff@{ORG}", role=UserRole.EMPLOYEE)
    svc = await services()

    code, output = await _run(
        svc, "deactivate", email=f"staff@{ORG}", actor=f"boss@{ORG}", yes=True
    )
    assert code == 0, output
    assert "revoked" in output

    async with app_db.state.test_session_factory() as session:
        after = await SqlAlchemyUserRepository(session).get(target.id)
    assert after.is_active is False


async def test_nobody_can_deactivate_themselves(services, app_db):
    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    svc = await services()
    code, _ = await _run(svc, "deactivate", email=f"boss@{ORG}", actor=f"boss@{ORG}", yes=True)
    assert code == 1


async def test_set_role_on_a_missing_account_points_at_pre_provision(services, app_db):
    await seed_user(app_db, email=f"boss@{ORG}", role=UserRole.SUPER_ADMIN)
    svc = await services()
    code, output = await _run(
        svc, "set-role", email=f"ghost@{ORG}", role=UserRole.ADMIN, actor=f"boss@{ORG}"
    )
    assert code == 1
    assert "pre-provision" in output


# --------------------------------------------------------------------------- #
# argv-level behaviour
# --------------------------------------------------------------------------- #
def test_deactivate_without_yes_is_a_usage_error():
    """Refused before any database work, so nothing can half-apply."""
    args = manage.build_parser().parse_args(
        ["deactivate", f"staff@{ORG}", "--actor", f"boss@{ORG}"]
    )
    assert args.yes is False, "--yes must not default to true"
    assert manage.EXIT_USAGE == 2


def test_every_documented_subcommand_exists():
    parser = manage.build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None)]
    assert actions, "no subcommands were registered"
    assert set(actions[0].choices) == set(manage.COMMANDS)


def test_role_is_parsed_into_the_enum_not_left_a_string():
    """The handlers pass args.role straight to a service expecting UserRole."""
    args = manage.build_parser().parse_args(
        ["set-role", f"staff@{ORG}", "--role", "MANAGER", "--actor", f"boss@{ORG}"]
    )
    assert args.role == "MANAGER"  # raw argv is a string...
    assert UserRole(args.role) is UserRole.MANAGER  # ...and converts cleanly
