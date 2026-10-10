"""Database backups: list, create on demand, restore.

Backups are ``pg_dump -Fc`` files in ``<data_dir>/backups`` (the updater
writes ``nestrisltm-<stamp>-before-<version>.dump`` before every install, the
admin can add ``nestrisltm-<stamp>-manual.dump``). Which schema a dump holds
is read from its ``alembic_version`` table with ``pg_restore``, so a dump is
"compatible" when this app knows that revision.

A restore never destroys data: the current database is renamed to
``<name>_pre_restore_<stamp>`` first and renamed back if the restore fails.
It only runs while the app is not connected (``DatabaseManager.maintenance``).
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import structlog

from nestris_ltm.config import DatabaseSettings, Settings
from nestris_ltm.db.bootstrap import connect_maintenance, known_revisions
from nestris_ltm.services.updates import find_pg_tool, prune_backups, run_pg_dump

log = structlog.get_logger(__name__)

RESTORE_TIMEOUT_S = 1800.0
INSPECT_TIMEOUT_S = 60.0
_NAME_RE = re.compile(r"^nestrisltm-(\d{8}-\d{6})(?:-before-(.+?)|-(manual))?\.dump$")
ASIDE_INFIX = "_pre_restore_"


class BackupError(Exception):
    """A backup or restore step failed; ``code`` is stable for the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BackupInfo:
    file: str
    size: int
    created_at: str
    kind: str  # "update" | "manual" | "other"
    before_version: str | None
    revision: str | None  # None = could not be read
    compatible: bool | None  # None = unknown (revision not readable)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def backup_dir(settings: Settings) -> Path:
    return settings.data_dir / "backups"


def _creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _pg_env(db: DatabaseSettings) -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": db.password.get_secret_value(), "PGCONNECT_TIMEOUT": "10"}


def parse_name(name: str) -> tuple[datetime | None, str, str | None]:
    """(timestamp, kind, before_version) from a backup file name."""
    m = _NAME_RE.match(name)
    if not m:
        return None, "other", None
    stamp = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
    if m.group(3):
        return stamp, "manual", None
    if m.group(2):
        return stamp, "update", m.group(2)
    return stamp, "other", None


def parse_alembic_copy(sql: str) -> str | None:
    """The revision from ``pg_restore --data-only -t alembic_version`` output."""
    lines = sql.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("COPY ") and "alembic_version" in line:
            for row in lines[i + 1 :]:
                if row == "\\.":
                    return None
                if row.strip():
                    return row.strip()
    return None


_revision_cache: dict[tuple[str, float, int], str | None] = {}


def dump_revision(pg_restore: str, dump: Path) -> str | None:
    """Schema revision stored in a dump (blocking; run in a thread)."""
    st = dump.stat()
    key = (str(dump), st.st_mtime, st.st_size)
    if key in _revision_cache:
        return _revision_cache[key]
    revision: str | None = None
    try:
        proc = subprocess.run(
            [pg_restore, "--data-only", "-t", "alembic_version", "-f", "-", str(dump)],
            capture_output=True,
            timeout=INSPECT_TIMEOUT_S,
            check=False,
            creationflags=_creationflags(),
        )
        if proc.returncode == 0:
            revision = parse_alembic_copy(proc.stdout.decode("utf-8", "replace"))
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("cannot inspect backup", file=dump.name, error=str(exc))
    _revision_cache[key] = revision
    return revision


def _list_sync(directory: Path, pg_restore: str | None, known: set[str]) -> list[BackupInfo]:
    if not directory.is_dir():
        return []
    out = []
    for dump in sorted(directory.glob("*.dump"), key=lambda p: p.stat().st_mtime, reverse=True):
        stamp, kind, before = parse_name(dump.name)
        st = dump.stat()
        created = stamp.astimezone() if stamp else datetime.fromtimestamp(st.st_mtime).astimezone()
        revision = dump_revision(pg_restore, dump) if pg_restore else None
        out.append(
            BackupInfo(
                file=dump.name,
                size=st.st_size,
                created_at=created.isoformat(),
                kind=kind,
                before_version=before,
                revision=revision,
                compatible=(revision in known) if revision else None,
            )
        )
    return out


async def list_backups(settings: Settings) -> list[BackupInfo]:
    pg_restore = find_pg_tool("pg_restore", settings.updates.pg_dump)
    return await asyncio.to_thread(_list_sync, backup_dir(settings), pg_restore, known_revisions())


def resolve_backup(settings: Settings, file: str) -> Path:
    """The backup file ``file`` (a bare name inside the backup directory)."""
    directory = backup_dir(settings).resolve()
    path = (directory / file).resolve()
    if path.parent != directory or path.suffix != ".dump" or not path.is_file():
        raise BackupError("not_found", f"backup {file!r} not found")
    return path


async def create_manual_backup(settings: Settings) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir(settings) / f"nestrisltm-{stamp}-manual.dump"
    try:
        dump = await run_pg_dump(settings, target)
    except Exception as exc:
        code = getattr(exc, "code", "backup_failed")
        raise BackupError(code, getattr(exc, "message", str(exc))) from exc
    prune_backups(backup_dir(settings))
    log.info("database backed up", path=str(dump))
    return dump


def aside_name(name: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S")
    suffix = f"{ASIDE_INFIX}{stamp}"
    return f"{name[: 63 - len(suffix)]}{suffix}"


async def aside_databases(db: DatabaseSettings) -> list[str]:
    """Databases left behind by earlier restores (``<name>_pre_restore_*``)."""
    conn = await connect_maintenance(db)
    try:
        rows = await conn.fetch(
            "SELECT datname FROM pg_database WHERE starts_with(datname, $1) ORDER BY datname",
            f"{db.name}{ASIDE_INFIX}",
        )
    finally:
        await conn.close()
    return [r["datname"] for r in rows]


async def _rename_away(conn: asyncpg.Connection, name: str, aside: str) -> None:
    for attempt in range(3):
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        try:
            await conn.execute(f'ALTER DATABASE "{name}" RENAME TO "{aside}"')
            return
        except asyncpg.ObjectInUseError:
            if attempt == 2:
                raise
            await asyncio.sleep(0.5)


async def restore_backup(settings: Settings, dump: Path) -> str | None:
    """Replace the app's database with ``dump``.

    Returns the name the previous database was kept under (None if there
    was none). Raises ``BackupError``; the previous database is back in
    place then.
    """
    db = settings.database
    pg_restore = find_pg_tool("pg_restore", settings.updates.pg_dump)
    if pg_restore is None:
        raise BackupError(
            "no_pg_restore",
            "pg_restore not found (PostgreSQL client tools; config updates.pg_dump)",
        )
    aside = aside_name(db.name)
    conn = await connect_maintenance(db)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db.name)
        if exists:
            await _rename_away(conn, db.name, aside)
            log.warning("database renamed for restore", database=db.name, kept_as=aside)
        await conn.execute(f"CREATE DATABASE \"{db.name}\" ENCODING 'UTF8'")
    finally:
        await conn.close()

    args = [
        pg_restore, "-h", db.host, "-p", str(db.port), "-U", db.user, "-d", db.name,
        "--no-owner", "--no-privileges", "--single-transaction", "--no-password", str(dump),
    ]  # fmt: skip

    def run() -> tuple[int, str]:
        try:
            proc = subprocess.run(
                args,
                env=_pg_env(db),
                capture_output=True,
                timeout=RESTORE_TIMEOUT_S,
                check=False,
                creationflags=_creationflags(),
            )
        except subprocess.TimeoutExpired:
            return -1, "pg_restore timed out"
        return proc.returncode, proc.stderr.decode("utf-8", "replace").strip()[-500:]

    code, detail = await asyncio.to_thread(run)
    if code != 0:
        conn = await connect_maintenance(db)
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{db.name}" WITH (FORCE)')
            if exists:
                await conn.execute(f'ALTER DATABASE "{aside}" RENAME TO "{db.name}"')
        finally:
            await conn.close()
        log.error("restore failed, previous database put back", error=detail)
        raise BackupError("restore_failed", f"pg_restore failed: {detail or code}")
    log.warning("database restored", database=db.name, backup=dump.name, kept_as=aside)
    return aside if exists else None
