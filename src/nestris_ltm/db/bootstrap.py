"""Bring the database to the current schema on startup.

1. Create the database itself if it does not exist yet.
2. Run all pending Alembic migrations, serialized by an advisory lock so
   two processes starting at once cannot migrate concurrently.

A schema revision this app does not know means a newer NestrisLTM migrated
the database: that raises ``SchemaTooNewError`` and leaves the database
untouched (an older app cannot downgrade, it lacks the newer migrations).
Every upgrade is logged in ``schema_history`` with the app version, so an
older app can tell which version the schema came from.
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

from nestris_ltm import __version__
from nestris_ltm.config import DatabaseSettings
from nestris_ltm.db.diagnosis import MigrationFailedError, SchemaTooNewError

log = structlog.get_logger(__name__)

# Arbitrary constant; identifies NestrisLTM's migration lock.
_MIGRATION_LOCK_ID = 0x4E4C544D  # "NLTM"


def migrations_dir() -> Path:
    return Path(str(resources.files("nestris_ltm.db") / "migrations"))


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir()))
    return cfg


async def connect_maintenance(settings: DatabaseSettings) -> asyncpg.Connection:
    """A plain connection to the server's ``postgres`` maintenance database."""
    return await asyncpg.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password.get_secret_value() or None,
        database="postgres",
        timeout=settings.connect_timeout_s,
    )


async def ensure_database(settings: DatabaseSettings) -> bool:
    """Create the configured database if missing. Returns True if created."""
    try:
        conn = await connect_maintenance(settings)
    except asyncpg.InvalidCatalogNameError:
        # No "postgres" database (or no access to it): the app's own database
        # may still exist; the engine's connect then tells the real story.
        return False
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


def _migrated_by(connection: Connection, revision: str) -> str | None:
    """App version that migrated to ``revision`` (``schema_history``, if present)."""
    if connection.execute(text("SELECT to_regclass('schema_history')")).scalar() is None:
        return None
    value = connection.execute(
        text(
            "SELECT app_version FROM schema_history WHERE revision = :rev"
            " ORDER BY migrated_at DESC LIMIT 1"
        ),
        {"rev": revision},
    ).scalar()
    return str(value) if value is not None else None


def _record_history(connection: Connection, revision: str | None) -> None:
    connection.execute(
        text("INSERT INTO schema_history (revision, app_version) VALUES (:rev, :ver)"),
        {"rev": revision, "ver": __version__},
    )


def known_revisions() -> set[str]:
    return {s.revision for s in ScriptDirectory.from_config(alembic_config()).walk_revisions()}


def app_head() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


async def migrate(engine: AsyncEngine) -> str | None:
    """Upgrade the schema to head. Returns the resulting revision.

    Raises ``SchemaTooNewError`` for a revision this app does not know and
    ``MigrationFailedError`` when an upgrade fails (rolled back).
    """
    cfg = alembic_config()
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    known = {s.revision for s in script.walk_revisions()}
    async with engine.begin() as conn:
        before = await conn.run_sync(_current_revision)
        if before is not None and before not in known:
            by = await conn.run_sync(_migrated_by, before)
            raise SchemaTooNewError(before, head, by)
        if before != head:
            log.info("migrating database schema", current=before, target=head)
            try:
                await conn.run_sync(_upgrade, cfg)
            except Exception as exc:
                raise MigrationFailedError(before, head, exc) from exc
            await conn.run_sync(_record_history, head)
    return head


async def bootstrap(settings: DatabaseSettings, engine: AsyncEngine) -> None:
    await ensure_database(settings)
    revision = await migrate(engine)
    log.info("database ready", database=settings.name, revision=revision)
