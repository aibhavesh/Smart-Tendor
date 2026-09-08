"""Alembic environment — async engine, metadata sourced from the ORM Base.

The DSN is taken from application Settings (environment), never from
alembic.ini, keeping the "no hardcoded secrets" rule intact.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

# Import the model registry so every table is attached to Base.metadata before
# autogenerate runs. (Populated from Phase 1 onward.)
import tender_intel.infrastructure.db.models  # noqa: F401
from tender_intel.core.config import get_settings
from tender_intel.infrastructure.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", str(get_settings().database_url))


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Render the custom UTCDateTime as its DDL impl so migrations need no app import."""
    from tender_intel.infrastructure.db.base import UTCDateTime

    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    from tender_intel.infrastructure.db.session import create_engine

    engine = create_engine(get_settings())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif (external := config.attributes.get("connection")) is not None:
    # Alembic's documented hook for running migrations against a connection the
    # caller already owns. The migration tests use it to drive the chain over a
    # throwaway SQLite database instead of the configured Postgres DSN.
    _do_run_migrations(external)
else:
    asyncio.run(run_migrations_online())
