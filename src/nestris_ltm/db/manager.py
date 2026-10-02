"""Owns the engine and keeps trying to bring the database up.

The app must start even when PostgreSQL is down (so the admin UI can show
the problem and fix the settings), therefore bootstrap runs in a background
task with backoff instead of failing startup.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nestris_ltm.config import DatabaseSettings
from nestris_ltm.db.bootstrap import bootstrap
from nestris_ltm.db.session import create_engine, create_session_factory

log = structlog.get_logger(__name__)


class DatabaseUnavailableError(RuntimeError):
    pass


class DatabaseManager:
    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self.engine = create_engine(settings)
        self.sessions: async_sessionmaker[AsyncSession] = create_session_factory(self.engine)
        self._ready = asyncio.Event()
        self.last_error: str | None = None
        self.ready_since: datetime | None = None

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    async def wait_ready(self, within_s: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._ready.wait(), within_s)
        except TimeoutError:
            return False
        return True

    async def run_bootstrap(self, *, max_backoff_s: float = 30.0) -> None:
        """Retry bootstrap until it succeeds (cancel the task to stop)."""
        delay = 1.0
        while True:
            try:
                await bootstrap(self.settings, self.engine)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("database not available, retrying", error=self.last_error, in_s=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_backoff_s)
            else:
                self.last_error = None
                self.ready_since = datetime.now(UTC)
                self._ready.set()
                return

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False
        return True

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if not self.is_ready:
            raise DatabaseUnavailableError(self.last_error or "database not ready")
        async with self.sessions() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
