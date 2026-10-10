"""Durable on-disk queue for station events.

The MQTT client acknowledges a QoS 1 message as soon as it was received, so
an event must be on disk before that point; otherwise a crash or a database
outage would lose a result for good. Each event is one JSON file, written
atomically (temp file + fsync + rename) and deleted once it is stored in the
database. Events that can never be stored (invalid payload) are moved to
``failed/`` for inspection instead of blocking the queue.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_NAME_RE = re.compile(r"\d{20}-\d{6}\.json")


@dataclass(frozen=True, slots=True)
class SpooledEvent:
    path: Path
    station: str
    kind: str  # e.g. "event/game_end"
    received_at: datetime
    payload: str


class EventSpool:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.failed_dir = directory / "failed"
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        self._counter = itertools.count()
        self._lock = threading.Lock()

    def append(self, station: str, kind: str, payload: str) -> Path:
        """Persist one event durably. Blocking; call via ``asyncio.to_thread``."""
        with self._lock:
            name = f"{time.time_ns():020d}-{next(self._counter) % 1_000_000:06d}.json"
        record = {
            "station": station,
            "kind": kind,
            "received_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        final = self.directory / name
        tmp = final.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(record, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, final)
        return final

    def pending(self) -> list[Path]:
        # Names start with a nanosecond timestamp, so sorting keeps arrival order.
        return sorted(self.directory.glob("*.json"))

    def failed(self) -> list[Path]:
        return sorted(self.failed_dir.glob("*.json"))

    @staticmethod
    def load(path: Path) -> SpooledEvent:
        record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return SpooledEvent(
            path=path,
            station=str(record["station"]),
            kind=str(record["kind"]),
            received_at=datetime.fromisoformat(record["received_at"]),
            payload=str(record["payload"]),
        )

    @staticmethod
    def complete(path: Path) -> None:
        path.unlink(missing_ok=True)

    def fail(self, path: Path, reason: str) -> Path:
        target = self.failed_dir / path.name
        os.replace(path, target)
        target.with_suffix(".reason.txt").write_text(reason, encoding="utf-8")
        return target

    # ------------------------------------------------------------ failed queue
    # The admin UI lists failed events and puts them back (after a fix, e.g. a
    # newer app that understands the payload) or discards them.

    @staticmethod
    def valid_name(name: str) -> bool:
        return _NAME_RE.fullmatch(name) is not None

    def failed_path(self, name: str) -> Path | None:
        if not self.valid_name(name):
            return None
        path = self.failed_dir / name
        return path if path.is_file() else None

    @staticmethod
    def reason(path: Path) -> str | None:
        note = path.with_suffix(".reason.txt")
        try:
            return note.read_text(encoding="utf-8")
        except OSError:
            return None

    def retry(self, name: str) -> bool:
        """Move a failed event back into the queue (keeps its arrival order)."""
        path = self.failed_path(name)
        if path is None:
            return False
        os.replace(path, self.directory / name)
        path.with_suffix(".reason.txt").unlink(missing_ok=True)
        return True

    def discard(self, name: str) -> bool:
        path = self.failed_path(name)
        if path is None:
            return False
        path.unlink(missing_ok=True)
        path.with_suffix(".reason.txt").unlink(missing_ok=True)
        return True

    def cleanup_temp(self) -> None:
        """Remove half-written files left by a crash during ``append``."""
        for tmp in self.directory.glob("*.tmp"):
            tmp.unlink(missing_ok=True)
