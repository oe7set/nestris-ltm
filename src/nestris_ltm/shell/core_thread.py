"""Runs the headless core (``Runtime.serve``) on a background thread."""

from __future__ import annotations

import threading

import structlog

from nestris_ltm.runtime import Runtime, run_async

log = structlog.get_logger(__name__)


class CoreThread(threading.Thread):
    def __init__(self, runtime: Runtime) -> None:
        super().__init__(name="nestris-core", daemon=True)
        self.runtime = runtime
        self.error: str | None = None
        self.finished = threading.Event()

    def run(self) -> None:
        try:
            run_async(self.runtime.serve())
        except BaseException as exc:  # incl. SystemExit from uvicorn on bind errors
            self.error = f"{type(exc).__name__}: {exc}"
            log.error("core stopped with an error", error=self.error)
        else:
            # uvicorn returns normally when it could not start (e.g. port in use).
            if not self.runtime.http_started and self.error is None:
                self.error = (
                    f"HTTP server could not start on port {self.runtime.settings.http.port} "
                    "(already in use?)"
                )
        finally:
            self.finished.set()

    def stop(self, timeout_s: float = 10.0) -> bool:
        """Request shutdown and wait. Returns True if the core stopped in time."""
        self.runtime.request_shutdown()
        return self.finished.wait(timeout_s)
