"""Alembic environment.

At runtime ``db.bootstrap`` hands over an open connection via
``config.attributes["connection"]``. Without one (developer CLI, e.g.
``alembic revision --autogenerate``) a connection is opened from the app
settings.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection

from nestris_ltm.db.models import Base

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_standalone() -> None:
    from nestris_ltm.config import load_settings
    from nestris_ltm.db.session import create_engine

    engine = create_engine(load_settings().database)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported")

connection = context.config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    asyncio.run(_run_standalone())
