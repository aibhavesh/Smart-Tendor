"""SQLAlchemy declarative base and shared column conventions.

Monetary and quantity columns use ``Numeric`` (exact decimal) end to end — never
float. All timestamps use :class:`UTCDateTime`, which guarantees timezone-aware
UTC values on result — SQLite (used in tests) otherwise returns naive datetimes,
which would compare-fail against the domain's aware ``datetime.now(UTC)``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now() -> datetime:
    """Timezone-aware UTC now, for column defaults and onupdate stamps."""
    return datetime.now(UTC)


# Explicit naming convention so Alembic autogenerate produces stable, named
# constraints (required for reliable downgrades).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware ``DateTime`` that normalises naive values to UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """``created_at`` / ``updated_at`` stamped from Python, not from the database.

    These used to be ``server_default=func.now()``, which is Postgres-only syntax:
    SQLite has no ``now()`` function, so any INSERT that omitted the columns (every
    one of them, since the ORM relies on the server default) failed with
    ``sqlite3.OperationalError: unknown function: now()``. Only ``User`` escaped it,
    because user_to_model() in repositories/mappers.py already stamps both values
    from the domain entity for exactly this reason.

    Python-side defaults fix it for every entity at once and on any dialect. The
    columns keep the ``now()`` server default in the existing schema, but the ORM
    now always supplies a value, so that default is never evaluated. Timestamps stay
    timezone-aware UTC, which UTCDateTime normalises consistently either way.
    """

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=_utc_now, onupdate=_utc_now, nullable=False
    )
