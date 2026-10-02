"""In-memory ring buffer of recent log records for the diagnostics view."""

from __future__ import annotations

import itertools
import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class LogEntry:
    id: int
    ts: datetime
    level: str
    logger: str
    message: str


class RingBufferHandler(logging.Handler):
    """Keeps the last ``capacity`` records; thread-safe."""

    def __init__(self, capacity: int) -> None:
        super().__init__()
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # never let logging break the caller
            self.handleError(record)
            return
        entry = LogEntry(
            id=next(self._ids),
            ts=datetime.fromtimestamp(record.created, tz=UTC),
            level=record.levelname,
            logger=record.name,
            message=message,
        )
        with self._lock:
            self._entries.append(entry)

    def entries(self, *, after_id: int = 0, min_level: int = logging.NOTSET) -> list[LogEntry]:
        with self._lock:
            snapshot = list(self._entries)
        return [
            e
            for e in snapshot
            if e.id > after_id and logging.getLevelNamesMapping()[e.level] >= min_level
        ]
