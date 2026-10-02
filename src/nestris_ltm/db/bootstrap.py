"""Bring the database to the current schema on startup.

1. Create the database itself if it does not exist yet.
2. Run all pending Alembic migrations, serialized by an advisory lock so
   two processes starting at once cannot migrate concurrently.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import asyncpg
import structlog
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from nestris_ltm.config import DatabaseSettings

log = structlog.get_logger(__name__)

# Arbitrary constant; identifies NestrisLTM's migration lock.
_MIGRATION_LOCK_ID = 0x4E4C544D  # "NLTM"


def migrations_dir() -> Path:
    return Path(str(resources.files("nestris_ltm.db") / "migrations"))


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir()))
    return cfg


async def ensure_database(settings: DatabaseSettings) -> bool:
    """Create the configured database if missing. Returns True if created."""
    conn = await asyncpg.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password.get_secret_value() or None,
        database="postgres",
        timeout=settings.connect_timeout_s,
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", settings.name)
        if exists:
            return False
        # The name is validated as a plain identifier in DatabaseSettings.
        await conn.execute(f"CREATE DATABASE \"{settings.name}\" ENCODING 'UTF8'")
        log.info("database created", database=settings.name)
        return True
    finally:
        await conn.close()


def _upgrade(connection: Connection, cfg: Config) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _MIGRATION_LOCK_ID})
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


def _current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


async def migrate(engine: AsyncEngine) -> str | None:
    """Upgrade the schema to head. Returns the resulting revision."""
    cfg = alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    async with engine.begin() as conn:
        before = await conn.run_sync(_current_revision)
        if before != head:
            log.info("migrating database schema", current=before, target=head)
            await conn.run_sync(_upgrade, cfg)
    return head


async def bootstrap(settings: DatabaseSettings, engine: AsyncEngine) -> None:
    await ensure_database(settings)
    revision = await migrate(engine)
    log.info("database ready", database=settings.name, revision=revision)
