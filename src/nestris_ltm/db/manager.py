"""Owns the engine and keeps trying to bring the database up.

The app must start even when PostgreSQL is down (so the admin UI can show
the problem and fix the settings), therefore bootstrap runs in a background
task with backoff instead of failing startup.

Failures are classified (``db/diagnosis.py``): transient ones are retried
with a short backoff, permanent ones (wrong password, schema newer than the
app) slowly, because they need an operator. ``retry_now()`` wakes the loop
after a fix; ``reconfigure()`` and ``maintenance()`` let the admin change the
connection or restore a backup while the database is not ready.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from nestris_ltm.config import DatabaseSettings
from nestris_ltm.db import diagnosis
from nestris_ltm.db.bootstrap import bootstrap
from nestris_ltm.db.diagnosis import DbProblem, classify, diagnose
from nestris_ltm.db.session import create_engine, create_session_factory

log = structlog.get_logger(__name__)

BootstrapFn = Callable[[DatabaseSettings, AsyncEngine], Awaitable[None]]


class DatabaseUnavailableError(RuntimeError):
    def __init__(self, state: str, detail: str | None = None) -> None:
        super().__init__(detail or "database not ready")
        self.state = state


class DatabaseManager:
    def __init__(
        self, settings: DatabaseSettings, *, bootstrap_fn: BootstrapFn = bootstrap
    ) -> None:
        self.settings = settings
        self._bootstrap = bootstrap_fn
        self.engine = create_engine(settings)
        self.sessions: async_sessionmaker[AsyncSession] = create_session_factory(self.engine)
        self._ready = asyncio.Event()
        self._wake = asyncio.Event()
        # Held by a bootstrap attempt, a restore and a reconfiguration, so
        # they never run at the same time.
        self._maintenance = asyncio.Lock()
        self._state = diagnosis.CONNECTING
        self.problem: DbProblem | None = None
        self.attempts = 0
        self.next_retry_at: datetime | None = None
        self.ready_since: datetime | None = None

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    @property
    def state(self) -> str:
        """``ready``, ``connecting``, ``restoring`` or a problem code."""
        if self.is_ready:
            return self.problem.state if self.problem else diagnosis.READY
        if self._state == diagnosis.RESTORING:
            return self._state
        return self.problem.state if self.problem else self._state

    @property
    def last_error(self) -> str | None:
        return self.problem.detail if self.problem else None

    async def wait_ready(self, within_s: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._ready.wait(), within_s)
        except TimeoutError:
            return False
        return True

    def retry_now(self) -> None:
        """Wake the bootstrap loop for an immediate attempt."""
        self._wake.set()

    def _set_problem(self, problem: DbProblem) -> None:
        changed = self.problem is None or (self.problem.state, self.problem.detail) != (
            problem.state,
            problem.detail,
        )
        self.problem = problem
        if changed:
            log.warning(
                "database not available",
                state=problem.state,
                error=problem.detail,
                hint=diagnosis.title(problem.state),
            )

    async def _sleep(self, seconds: float) -> bool:
        """Sleep up to ``seconds``; True if ``retry_now()`` cut it short."""
        self.next_retry_at = datetime.now(UTC) + timedelta(seconds=seconds)
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except TimeoutError:
            return False
        finally:
            self.next_retry_at = None
        return True

    async def run_bootstrap(
        self, *, max_backoff_s: float = 30.0, permanent_retry_s: float = 60.0
    ) -> None:
        """Retry bootstrap until it succeeds (cancel the task to stop)."""
        delay = 1.0
        while True:
            self._wake.clear()
            self.attempts += 1
            try:
                async with self._maintenance:
                    await self._bootstrap(self.settings, self.engine)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                problem = await diagnose(exc, self.settings)
                self._set_problem(problem)
                wait = permanent_retry_s if problem.permanent else delay
                log.debug("database retry scheduled", state=problem.state, in_s=wait)
                if await self._sleep(wait):
                    delay = 1.0
                elif not problem.permanent:
                    delay = min(delay * 2, max_backoff_s)
            else:
                if self.problem is not None:
                    log.info("database ready after problem", was=self.problem.state)
                self.problem = None
                self._state = diagnosis.READY
                self.ready_since = datetime.now(UTC)
                self._ready.set()
                return

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            self._set_problem(classify(exc))
            return False
        if self.is_ready:
            self.problem = None
        return True

    @asynccontextmanager
    async def maintenance(self) -> AsyncIterator[None]:
        """Exclusive use of the database while it is not ready (e.g. a restore).

        The pool is closed first, so no connection of ours stays open on the
        database; afterwards the bootstrap loop retries at once.
        """
        if self.is_ready:
            raise RuntimeError("the database is in use; maintenance needs it not ready")
        async with self._maintenance:
            previous = self._state
            self._state = diagnosis.RESTORING
            try:
                await self.engine.dispose()
                yield
            finally:
                self._state = previous
                self.retry_now()

    async def reconfigure(self, settings: DatabaseSettings) -> None:
        """Switch to new connection settings (only while not ready)."""
        if self.is_ready:
            raise RuntimeError("the database is connected; restart to change the connection")
        async with self._maintenance:
            old = self.engine
            self.settings = settings
            self.engine = create_engine(settings)
            self.sessions = create_session_factory(self.engine)
            self.problem = None
            self._state = diagnosis.CONNECTING
            await old.dispose()
        self.retry_now()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if not self.is_ready:
            raise DatabaseUnavailableError(self.state, self.last_error)
        async with self.sessions() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
