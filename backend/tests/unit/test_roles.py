"""The four-role hierarchy, and a guard against the old five-role vocabulary."""

from __future__ import annotations

import re
from itertools import permutations
from pathlib import Path

import pytest

from tender_intel.domain.enums.roles import ELEVATED_ROLES, UserRole

_SRC = Path(__file__).resolve().parents[2] / "src"
_TESTS = Path(__file__).resolve().parents[1]


def test_exactly_four_roles():
    assert set(UserRole) == {
        UserRole.EMPLOYEE,
        UserRole.MANAGER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    }


def test_levels_are_the_documented_values():
    assert UserRole.EMPLOYEE.level == 20
    assert UserRole.MANAGER.level == 30
    assert UserRole.ADMIN.level == 40
    assert UserRole.SUPER_ADMIN.level == 50


def test_level_ordering_is_strict():
    ordered = [UserRole.EMPLOYEE, UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN]
    assert [r.level for r in ordered] == sorted(r.level for r in ordered)
    assert len({r.level for r in ordered}) == 4


@pytest.mark.parametrize("role", list(UserRole))
def test_every_role_can_act_as_itself(role: UserRole):
    assert role.can_act_as(role)


@pytest.mark.parametrize(("higher", "lower"), list(permutations(list(UserRole), 2)))
def test_comparison_is_inclusive_upward_only(higher: UserRole, lower: UserRole):
    """A role admits everything at or below its level, and nothing above it."""
    if higher.level > lower.level:
        assert higher.can_act_as(lower)
        assert not lower.can_act_as(higher)


def test_employee_is_the_floor():
    assert min(r.level for r in UserRole) == UserRole.EMPLOYEE.level
    assert all(r.can_act_as(UserRole.EMPLOYEE) for r in UserRole)


def test_elevated_roles_excludes_the_floor():
    assert {UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN} == ELEVATED_ROLES
    assert UserRole.EMPLOYEE not in ELEVATED_ROLES


#: The two files that must still name the retired roles. Migrations rewrite the
#: old values and cannot do so without naming them, and the tests that drive
#: those migrations have to seed rows holding them. The migration modules
#: themselves live outside ``src`` and ``tests`` and are never scanned.
_EXEMPT = {"test_roles.py", "test_migrations.py"}


def _python_files():
    for root in (_SRC, _TESTS):
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or path.name in _EXEMPT:
                continue
            yield path


def test_no_analyst_or_viewer_reference_survives():
    """ANALYST and VIEWER are gone; nothing may still name them as roles.

    Matched on word boundaries so prose in a comment is caught too — the
    vocabulary should not linger in live code, only in the migration that
    retires it.
    """
    pattern = re.compile(r"\b(ANALYST|VIEWER)\b")
    offenders: list[str] = []
    for path in _python_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert not offenders, "stale role names found:\n" + "\n".join(offenders)
