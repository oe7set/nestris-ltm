from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import IntegrityError

from nestris_ltm.config import DatabaseSettings
from nestris_ltm.db.bootstrap import bootstrap, ensure_database
from nestris_ltm.db.models import Base
from nestris_ltm.db.session import create_engine

pytestmark = pytest.mark.db


async def test_bootstrap_creates_database_and_schema(fresh_db_settings: DatabaseSettings) -> None:
    engine = create_engine(fresh_db_settings)
    try:
        await bootstrap(fresh_db_settings, engine)

        async with engine.connect() as conn:
            tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        assert set(Base.metadata.tables) <= tables
        assert "alembic_version" in tables
    finally:
        await engine.dispose()


async def test_bootstrap_is_idempotent(fresh_db_settings: DatabaseSettings) -> None:
    engine = create_engine(fresh_db_settings)
    try:
        await bootstrap(fresh_db_settings, engine)
        await bootstrap(fresh_db_settings, engine)
        assert await ensure_database(fresh_db_settings) is False
    finally:
        await engine.dispose()


async def test_migrations_match_models(fresh_db_settings: DatabaseSettings) -> None:
    """Fails when a model changed without a new Alembic revision."""

    def diff(conn: Connection) -> list[object]:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return list(compare_metadata(ctx, Base.metadata))

    engine = create_engine(fresh_db_settings)
    try:
        await bootstrap(fresh_db_settings, engine)
        async with engine.connect() as conn:
            assert await conn.run_sync(diff) == []
    finally:
        await engine.dispose()


async def test_schema_constraints(fresh_db_settings: DatabaseSettings) -> None:
    engine = create_engine(fresh_db_settings)
    try:
        await bootstrap(fresh_db_settings, engine)

        # Nicknames are unique case-insensitively among non-deleted players.
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO players (nickname) VALUES ('Erv')"))
            await conn.execute(text("UPDATE players SET deleted_at = now()"))
            await conn.execute(text("INSERT INTO players (nickname) VALUES ('ERV')"))
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(text("INSERT INTO players (nickname) VALUES ('erv')"))

        # Only one active event.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO events (name, slug, starts_at, is_active) "
                    "VALUES ('A', 'a', now(), true)"
                )
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO events (name, slug, starts_at, is_active) "
                        "VALUES ('B', 'b', now(), true)"
                    )
                )

        # Game status is constrained.
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text("INSERT INTO games (status, started_at) VALUES ('bogus', now())")
                )
    finally:
        await engine.dispose()
