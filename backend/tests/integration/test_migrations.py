"""The Alembic chain, driven end to end over a throwaway SQLite database.

The rest of the suite builds its schema with ``Base.metadata.create_all``, which
never exercises a migration. These tests are the only place the upgrade path
itself runs, so they are what catches a data migration that does not do what its
docstring claims.

The initial migration uses no PostgreSQL-specific types, so SQLite is a faithful
enough stand-in for the DDL and for the ``UPDATE`` statements under test.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from tender_intel.core.config import get_settings

_BACKEND = Path(__file__).resolve().parents[2]
_INITIAL = "df21fab595ca"  # base schema, before the role collapse
_COLLAPSE_ROLES = "a1c4e07b91d2"
_BEFORE_BOOTSTRAP = "c2d8b6f4173a"  # role_assignments exists, nothing seeded
_BEFORE_SPLIT = "d4a1e9c5b872"  # tender_reviews still requires a verdict
_SPLIT = "e7c3a5d18f92"  # hashed_password still absent
_RESTORE_PASSWORD = "7690fc277a01"


def _alembic_config(connection: sa.Connection) -> Config:
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[sa.Engine]:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migrations.db'}")
    yield engine
    engine.dispose()


def _upgrade(engine: sa.Engine, revision: str) -> None:
    with engine.begin() as connection:
        command.upgrade(_alembic_config(connection), revision)


def _downgrade(engine: sa.Engine, revision: str) -> None:
    with engine.begin() as connection:
        command.downgrade(_alembic_config(connection), revision)


def _insert_user(
    connection: sa.Connection, email: str, role: str, *, with_password: bool = True
) -> uuid.UUID:
    """Insert a user row.

    ``with_password`` must be False at any revision from ``b7f39d5a2e60``
    (which drops the column) up to but not including ``7690fc277a01`` (which
    restores it).
    """
    user_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat(sep=" ")
    password_column = ", hashed_password" if with_password else ""
    password_value = ", 'bcrypt-hash'" if with_password else ""
    connection.execute(
        sa.text(
            f"INSERT INTO users (id, email, full_name, role{password_column}, google_sub, "
            "is_active, last_login_at, created_at, updated_at) "
            f"VALUES (:id, :email, 'Seeded', :role{password_value}, NULL, 1, NULL, :now, :now)"
        ),
        {"id": str(user_id), "email": email, "role": role, "now": now},
    )
    return user_id


def _role_of(engine: sa.Engine, email: str) -> str | None:
    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT role FROM users WHERE email = :email"), {"email": email}
        ).first()
    return row[0] if row else None


# --- The role collapse --- #
@pytest.mark.parametrize("legacy_role", ["ANALYST", "VIEWER"])
def test_legacy_roles_become_employee(engine: sa.Engine, legacy_role: str):
    _upgrade(engine, _INITIAL)  # the revision *before* the collapse
    with engine.begin() as connection:
        _insert_user(connection, f"{legacy_role.lower()}@x.com", legacy_role)

    _upgrade(engine, "head")

    assert _role_of(engine, f"{legacy_role.lower()}@x.com") == "EMPLOYEE"


def test_untouched_roles_survive_the_collapse(engine: sa.Engine):
    _upgrade(engine, _INITIAL)
    with engine.begin() as connection:
        for role in ("MANAGER", "ADMIN", "SUPER_ADMIN"):
            _insert_user(connection, f"{role.lower()}@x.com", role)

    _upgrade(engine, "head")

    for role in ("MANAGER", "ADMIN", "SUPER_ADMIN"):
        assert _role_of(engine, f"{role.lower()}@x.com") == role


def test_downgrade_of_the_collapse_lands_on_the_lower_role(engine: sa.Engine):
    """The split is unrecoverable; the downgrade under-grants rather than over-grants."""
    _upgrade(engine, _INITIAL)
    with engine.begin() as connection:
        _insert_user(connection, "analyst@x.com", "ANALYST")
    _upgrade(engine, "head")

    _downgrade(engine, _INITIAL)

    assert _role_of(engine, "analyst@x.com") == "VIEWER"


# --- Schema shape at head --- #
def test_password_column_is_present_and_nullable_and_role_assignments_exist(engine: sa.Engine):
    _upgrade(engine, "head")

    inspector = sa.inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("users")}
    # Nullable: a Google-only account never gets one, and none is required.
    assert columns["hashed_password"]["nullable"] is True
    assert "role_assignments" in inspector.get_table_names()

    columns = {c["name"]: c for c in inspector.get_columns("role_assignments")}
    assert set(columns) == {
        "id",
        "email",
        "role",
        "assigned_by",
        "assigned_at",
        "consumed_at",
        "consumed_user_id",
    }
    # The bootstrap row has no human assigner, so this must be nullable.
    assert columns["assigned_by"]["nullable"] is True


# --- Restoring password authentication --- #
def test_password_column_absent_before_the_restore(engine: sa.Engine):
    _upgrade(engine, _SPLIT)
    inspector = sa.inspect(engine)
    assert "hashed_password" not in {c["name"] for c in inspector.get_columns("users")}


def test_password_column_added_nullable_and_existing_rows_survive(engine: sa.Engine):
    _upgrade(engine, _SPLIT)
    with engine.begin() as connection:
        _insert_user(connection, "google-only@x.com", "EMPLOYEE", with_password=False)

    _upgrade(engine, _RESTORE_PASSWORD)

    inspector = sa.inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("users")}
    assert columns["hashed_password"]["nullable"] is True
    with engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT hashed_password FROM users WHERE email = :email"),
            {"email": "google-only@x.com"},
        ).first()
    assert row is not None
    assert row[0] is None


def test_downgrade_of_the_restore_drops_the_column_again(engine: sa.Engine):
    _upgrade(engine, _RESTORE_PASSWORD)
    _downgrade(engine, _SPLIT)
    inspector = sa.inspect(engine)
    assert "hashed_password" not in {c["name"] for c in inspector.get_columns("users")}


# --- The correction/verdict split --- #
def _insert_tender(connection: sa.Connection, number: str) -> uuid.UUID:
    tender_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat(sep=" ")
    connection.execute(
        sa.text(
            "INSERT INTO tenders (id, tender_number, title, status, description, "
            "estimated_value, closing_date, source_url, department, created_at, updated_at) "
            "VALUES (:id, :number, 'T', 'ANALYZED', NULL, NULL, NULL, NULL, NULL, :now, :now)"
        ),
        {"id": str(tender_id), "number": number, "now": now},
    )
    return tender_id


def _insert_legacy_review(
    connection: sa.Connection, tender_id: uuid.UUID, reviewer_id: uuid.UUID, verdict: str
) -> uuid.UUID:
    """A row in the pre-split shape: verdict NOT NULL, no ``kind`` column."""
    review_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO tender_reviews (id, tender_id, reviewer_id, verdict, comments, "
            "before_snapshot, after_snapshot, created_at) "
            "VALUES (:id, :tender_id, :reviewer_id, :verdict, NULL, '{}', '{}', :now)"
        ),
        {
            "id": str(review_id),
            "tender_id": str(tender_id),
            "reviewer_id": str(reviewer_id),
            "verdict": verdict,
            "now": datetime.now(UTC).isoformat(sep=" "),
        },
    )
    return review_id


def test_existing_reviews_backfill_as_verdict(engine: sa.Engine):
    """Exact, not a guess: the only writer required a verdict."""
    _upgrade(engine, _BEFORE_SPLIT)
    with engine.begin() as connection:
        reviewer = _insert_user(connection, "m@x.com", "MANAGER", with_password=False)
        tender = _insert_tender(connection, "T-1")
        _insert_legacy_review(connection, tender, reviewer, "APPROVED")
        _insert_legacy_review(connection, tender, reviewer, "REJECTED")

    _upgrade(engine, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            sa.text("SELECT kind, verdict FROM tender_reviews ORDER BY verdict")
        ).all()
    assert [(r[0], r[1]) for r in rows] == [("VERDICT", "APPROVED"), ("VERDICT", "REJECTED")]


def test_verdict_becomes_nullable_and_kind_is_indexed(engine: sa.Engine):
    _upgrade(engine, "head")

    inspector = sa.inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("tender_reviews")}
    assert columns["verdict"]["nullable"] is True
    assert columns["kind"]["nullable"] is False
    indexed = {tuple(i["column_names"]) for i in inspector.get_indexes("tender_reviews")}
    assert ("kind",) in indexed


def test_downgrade_deletes_corrections_and_restores_not_null(engine: sa.Engine):
    """Documented data loss: the old schema cannot represent a correction."""
    _upgrade(engine, "head")
    with engine.begin() as connection:
        reviewer = _insert_user(connection, "m@x.com", "MANAGER", with_password=False)
        tender = _insert_tender(connection, "T-1")
        now = datetime.now(UTC).isoformat(sep=" ")
        connection.execute(
            sa.text(
                "INSERT INTO tender_reviews (id, tender_id, reviewer_id, kind, verdict, "
                "comments, before_snapshot, after_snapshot, created_at) VALUES "
                "(:c, :t, :r, 'CORRECTION', NULL, NULL, '{}', '{}', :now), "
                "(:v, :t, :r, 'VERDICT', 'APPROVED', NULL, '{}', '{}', :now)"
            ),
            {
                "c": str(uuid.uuid4()),
                "v": str(uuid.uuid4()),
                "t": str(tender),
                "r": str(reviewer),
                "now": now,
            },
        )

    _downgrade(engine, _BEFORE_SPLIT)

    with engine.connect() as connection:
        rows = connection.execute(sa.text("SELECT verdict FROM tender_reviews")).all()
        columns = {c["name"]: c for c in sa.inspect(engine).get_columns("tender_reviews")}
    assert [r[0] for r in rows] == ["APPROVED"]  # the correction is gone
    assert "kind" not in columns
    assert columns["verdict"]["nullable"] is False


# --- Bootstrap --- #
@pytest.fixture
def bootstrap_email() -> Iterator[str]:
    """Point BOOTSTRAP_SUPER_ADMIN_EMAIL at a test address for one test."""
    email = "founder@maheshwaricomputers.com"
    previous = os.environ.get("BOOTSTRAP_SUPER_ADMIN_EMAIL")
    os.environ["BOOTSTRAP_SUPER_ADMIN_EMAIL"] = email.upper()  # also proves normalisation
    get_settings.cache_clear()
    try:
        yield email
    finally:
        if previous is None:
            os.environ.pop("BOOTSTRAP_SUPER_ADMIN_EMAIL", None)
        else:
            os.environ["BOOTSTRAP_SUPER_ADMIN_EMAIL"] = previous
        get_settings.cache_clear()


def _assignments(engine: sa.Engine, email: str) -> list[tuple[str, str]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1])
            for row in connection.execute(
                sa.text("SELECT email, role FROM role_assignments WHERE email = :email"),
                {"email": email},
            )
        ]


def test_bootstrap_seeds_a_super_admin_assignment(engine: sa.Engine, bootstrap_email: str):
    _upgrade(engine, "head")
    assert _assignments(engine, bootstrap_email) == [(bootstrap_email, "SUPER_ADMIN")]


def test_bootstrap_is_idempotent(engine: sa.Engine, bootstrap_email: str):
    _upgrade(engine, "head")
    # Re-running the final revision must not add a second row.
    _downgrade(engine, _BEFORE_BOOTSTRAP)
    _upgrade(engine, "head")
    _upgrade(engine, "head")
    assert _assignments(engine, bootstrap_email) == [(bootstrap_email, "SUPER_ADMIN")]


def test_bootstrap_skips_when_the_account_already_exists(engine: sa.Engine, bootstrap_email: str):
    _upgrade(engine, _BEFORE_BOOTSTRAP)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, email, full_name, role, google_sub, is_active, "
                "last_login_at, created_at, updated_at) "
                "VALUES (:id, :email, 'Founder', 'EMPLOYEE', NULL, 1, NULL, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "email": bootstrap_email,
                "now": datetime.now(UTC).isoformat(sep=" "),
            },
        )

    _upgrade(engine, "head")

    # Seeding here would create a row that can never be consumed.
    assert _assignments(engine, bootstrap_email) == []


def test_bootstrap_is_a_no_op_without_configuration(engine: sa.Engine):
    # Set empty rather than unset: Settings falls back to backend/.env, so
    # deleting the variable would let a developer's own configuration decide
    # whether this test passes.
    previous = os.environ.get("BOOTSTRAP_SUPER_ADMIN_EMAIL")
    os.environ["BOOTSTRAP_SUPER_ADMIN_EMAIL"] = ""
    get_settings.cache_clear()
    try:
        _upgrade(engine, "head")
        with engine.connect() as connection:
            total = connection.execute(
                sa.text("SELECT count(*) FROM role_assignments")
            ).scalar_one()
        assert total == 0
    finally:
        if previous is None:
            os.environ.pop("BOOTSTRAP_SUPER_ADMIN_EMAIL", None)
        else:
            os.environ["BOOTSTRAP_SUPER_ADMIN_EMAIL"] = previous
        get_settings.cache_clear()
