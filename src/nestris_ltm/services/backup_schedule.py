"""Automatic database backups during an event.

Settings (``backup.schedule`` in the settings table, edited in the admin UI):

- ``interval_min``: 0 = off, else minutes between two backups;
- ``only_during_event``: back up only while an event is active (default);
- ``copy_dir``: optional second folder (e.g. a USB stick or another disk)
  that receives a copy of each automatic backup.

Automatic dumps are named ``nestrisltm-<stamp>-auto.dump`` and pruned
separately (``AUTO_KEPT``), so they never push out the update and manual ones.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

from nestris_ltm.services import app_settings, db_backup, events
from nestris_ltm.services.updates import run_pg_dump

if TYPE_CHECKING:
    from nestris_ltm.runtime import Runtime

log = structlog.get_logger(__name__)

KEY = "backup.schedule"
AUTO_KEPT = 24
CHECK_EVERY_S = 60.0


class ScheduleSettings(BaseModel):
    interval_min: int = Field(default=0, ge=0, le=24 * 60)
    only_during_event: bool = True
    copy_dir: str = Field(default="", max_length=400)


def prune_auto(directory: Path, keep: int = AUTO_KEPT) -> None:
    dumps = sorted(directory.glob("nestrisltm-*-auto.dump"), key=lambda p: p.stat().st_mtime)
    for old in dumps[: max(0, len(dumps) - keep)]:
        with contextlib.suppress(OSError):
            old.unlink()


class BackupSchedule:
    def __init__(self, runtime: Runtime) -> None:
        self.rt = runtime
        self.settings = ScheduleSettings()
        self.last_at: datetime | None = None
        self.last_file: str | None = None
        self.last_error: str | None = None
        self.last_copy_error: str | None = None
        self._wake = asyncio.Event()

    def state(self) -> dict[str, Any]:
        next_at = None
        if self.settings.interval_min and self.last_at is not None:
            next_at = (self.last_at + timedelta(minutes=self.settings.interval_min)).isoformat()
        return {
            **self.settings.model_dump(),
            "last_at": self.last_at.isoformat() if self.last_at else None,
            "last_file": self.last_file,
            "last_error": self.last_error,
            "last_copy_error": self.last_copy_error,
            "next_at": next_at,
        }

    async def load(self) -> None:
        async with self.rt.db.session() as session:
            stored = await app_settings.get(session, KEY)
        if stored:
            self.settings = ScheduleSettings.model_validate(stored)

    async def update(self, new: ScheduleSettings) -> None:
        async with self.rt.db.session() as session, session.begin():
            await app_settings.put(session, KEY, new.model_dump())
        self.settings = new
        self._wake.set()

    async def _due(self) -> bool:
        cfg = self.settings
        if not cfg.interval_min or not self.rt.db.is_ready:
            return False
        if cfg.only_during_event:
            async with self.rt.db.session() as session:
                if await events.active_event(session) is None:
                    return False
        if self.last_at is None:
            return True
        return datetime.now(UTC) - self.last_at >= timedelta(minutes=cfg.interval_min)

    async def run_once(self) -> Path:
        directory = db_backup.backup_dir(self.rt.settings)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = directory / f"nestrisltm-{stamp}-auto.dump"
        self.last_at = datetime.now(UTC)
        try:
            dump = await run_pg_dump(self.rt.settings, target)
        except Exception as exc:
            self.last_error = getattr(exc, "message", str(exc))
            log.error("automatic backup failed", error=self.last_error)
            raise
        self.last_error = None
        self.last_file = dump.name
        prune_auto(directory)
        log.info("automatic backup", path=str(dump))
        if self.settings.copy_dir:
            await self._copy(dump, Path(self.settings.copy_dir))
        return dump

    async def _copy(self, dump: Path, folder: Path) -> None:
        def copy() -> None:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dump, folder / dump.name)
            prune_auto(folder)

        try:
            await asyncio.to_thread(copy)
            self.last_copy_error = None
        except OSError as exc:
            # A missing USB stick must not stop the backups themselves.
            self.last_copy_error = f"{folder}: {exc}"
            log.warning("backup copy failed", error=self.last_copy_error)

    async def run(self) -> None:
        await self.rt.db.wait_ready()
        with contextlib.suppress(Exception):
            await self.load()
        while True:
            try:
                if await self._due():
                    await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # reported in state(); try again next round
                log.debug("backup schedule round failed", error=repr(exc))
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), CHECK_EVERY_S)
