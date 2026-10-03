"""The headless core: owns all long-running services and the HTTP server.

``Runtime.serve()`` is the single entry point used both by ``--headless``
and by the Qt shell (which runs it on a background thread).
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import sys
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import structlog
import uvicorn

from nestris_ltm.config import Settings
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.ingest.frame_buffer import FrameBuffer
from nestris_ltm.ingest.mqtt_client import MqttIngest
from nestris_ltm.ingest.service import IngestService
from nestris_ltm.ingest.spool import EventSpool
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services.scenes import SceneEngine
from nestris_ltm.services.tournament import TournamentService

log = structlog.get_logger(__name__)


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """``asyncio.run`` with a selector loop on Windows.

    The MQTT client (paho) needs ``add_reader``/``add_writer``, which the
    default Windows proactor loop does not implement.
    """
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(coro)


class Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.started_at = datetime.now(UTC)
        self.db = DatabaseManager(settings.database)
        self.hub = LiveHub()
        self.spool = EventSpool(settings.data_dir / "spool")
        self.frames = FrameBuffer(self.db)
        self.ingest = IngestService(self.db, self.hub, self.frames, self.spool)
        self.mqtt = MqttIngest(settings.mqtt, self.ingest)
        self.tournament = TournamentService(self.db, self.hub)
        self.scenes = SceneEngine(self.db, self.hub)
        # Sent by the Qt shell's embedded browser; grants an admin session
        # without a login (the shell runs on the host itself).
        self.shell_token = secrets.token_urlsafe(32)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._server: uvicorn.Server | None = None

    @property
    def http_started(self) -> bool:
        """True once the HTTP server accepts connections."""
        return self._server is not None and self._server.started

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.settings.http.port}"

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
        self.spawn(self.mqtt.run(), name="mqtt")
        self.spawn(self.ingest.run_worker(), name="event-worker")
        self.spawn(self.ingest.run_station_sync(), name="station-sync")
        self.spawn(self.ingest.run_sweeper(), name="sweeper")
        self.spawn(self.frames.run(), name="frame-buffer")
        self.spawn(self.tournament.run(), name="kiosk")
        self.spawn(self.scenes.run(), name="scenes")

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        # Write whatever live frames and round results are still buffered.
        if self.db.is_ready:
            with contextlib.suppress(Exception):
                await self.frames.flush()
            await self.scenes.close()
        await self.db.dispose()

    async def serve(self) -> None:
        from nestris_ltm.api.app import create_app

        self.loop = asyncio.get_running_loop()
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
        """Ask the HTTP server (and with it the runtime) to stop. Thread-safe."""
        loop = self.loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._stop_server)
        else:
            self._stop_server()

    def _stop_server(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
