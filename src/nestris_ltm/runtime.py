"""The headless core: owns all long-running services and the HTTP server.

``Runtime.serve()`` is the single entry point used both by ``--headless``
and by the Qt shell (which runs it on a background thread).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Coroutine
from typing import Any

import structlog
import uvicorn

from nestris_ltm.config import Settings
from nestris_ltm.db.manager import DatabaseManager

log = structlog.get_logger(__name__)


class Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = DatabaseManager(settings.database)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._server: uvicorn.Server | None = None

    def spawn(self, coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        """Start a background task that is cancelled on shutdown."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            log.error("background task crashed", task=task.get_name(), error=repr(exc))

    async def start(self) -> None:
        self.spawn(self.db.run_bootstrap(), name="db-bootstrap")

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await self.db.dispose()

    async def serve(self) -> None:
        from nestris_ltm.api.app import create_app

        app = create_app(self)
        config = uvicorn.Config(
            app,
            host=self.settings.http.host,
            port=self.settings.http.port,
            log_config=None,  # keep our logging setup
            access_log=False,
            ws_ping_interval=20,
            ws_ping_timeout=20,
        )
        self._server = uvicorn.Server(config)
        log.info("http server starting", host=config.host, port=config.port)
        await self._server.serve()

    def request_shutdown(self) -> None:
        """Thread-unsafe; call via loop.call_soon_threadsafe from other threads."""
        if self._server is not None:
            self._server.should_exit = True
