"""Logging: structlog on top of the stdlib, console + rotating file + ring buffer."""

from __future__ import annotations

import logging
import logging.handlers
import sys

import structlog

from nestris_ltm.config import Settings
from nestris_ltm.diagnostics.logbuffer import RingBufferHandler

_ring: RingBufferHandler | None = None


def ring_buffer() -> RingBufferHandler | None:
    """The diagnostics ring buffer, once logging is configured."""
    return _ring


def configure_logging(settings: Settings) -> None:
    global _ring

    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    def formatter(renderer: structlog.types.Processor) -> logging.Formatter:
        return structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )

    plain = formatter(structlog.dev.ConsoleRenderer(colors=False))
    handlers: list[logging.Handler] = []

    # A windowed (PyInstaller --noconsole) build has no stderr.
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())))
        handlers.append(console)

    if settings.log.to_file:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_dir / "nestris-ltm.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter(structlog.processors.JSONRenderer()))
        handlers.append(file_handler)

    _ring = RingBufferHandler(settings.log.buffer_size)
    _ring.setFormatter(plain)
    handlers.append(_ring)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(settings.log.level)

    # Third-party loggers that are too chatty at INFO.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
