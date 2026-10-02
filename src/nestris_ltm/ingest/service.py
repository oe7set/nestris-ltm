"""Turns MQTT messages into live state and database rows.

Message routing (topics below ``<prefix>/<station>/``):

- ``status``, ``player``  -> LiveHub (memory); stations are synced to the DB
  in the background.
- ``live``                -> LiveHub + FrameBuffer (batched DB writes).
- ``event/*``             -> durable spool -> worker -> database. The worker
  is the only writer of game rows, so events are applied strictly in order.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from nestris_ltm.db.manager import DatabaseManager, DatabaseUnavailableError
from nestris_ltm.db.models import Station
from nestris_ltm.ingest.frame_buffer import FrameBuffer
from nestris_ltm.ingest.payloads import (
    CheatPayload,
    GameEndPayload,
    GameStartPayload,
    LivePayload,
    PlayerPayload,
    StatusPayload,
)
from nestris_ltm.ingest.spool import EventSpool, SpooledEvent
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services import games, players

log = structlog.get_logger(__name__)

EVENT_KINDS = ("event/game_start", "event/cheat", "event/game_end")
MAX_ATTEMPTS = 5
RETRY_DELAY_S = 5.0
STATION_SYNC_INTERVAL_S = 5.0
SWEEP_INTERVAL_S = 600.0
ABANDON_AFTER = timedelta(hours=3)

_TRANSIENT = (DatabaseUnavailableError, OperationalError, InterfaceError, OSError, TimeoutError)


class PermanentEventError(Exception):
    """The event can never be stored (bad payload); it goes to spool/failed."""


@dataclass
class IngestStats:
    messages: dict[str, int] = field(default_factory=dict)
    parse_errors: int = 0
    last_parse_error: str | None = None
    events_stored: int = 0
    events_failed: int = 0
    last_event_error: str | None = None

    def count(self, kind: str) -> None:
        self.messages[kind] = self.messages.get(kind, 0) + 1


def split_topic(topic: str, prefix: str) -> tuple[str, str] | None:
    """``<prefix>/<station>/<kind...>`` -> ``(station, kind)``."""
    head = prefix.rstrip("/") + "/"
    if not topic.startswith(head):
        return None
    station, _, kind = topic[len(head) :].partition("/")
    if not station or not kind:
        return None
    return station, kind


class IngestService:
    def __init__(
        self, db: DatabaseManager, hub: LiveHub, frames: FrameBuffer, spool: EventSpool
    ) -> None:
        self.db = db
        self.hub = hub
        self.frames = frames
        self.spool = spool
        self.stats = IngestStats()
        self._wake = asyncio.Event()
        self._attempts: dict[str, int] = {}
        self._dirty_stations: set[str] = set()
        self._background: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------ MQTT side

    async def handle_message(self, topic: str, payload: bytes | str, prefix: str) -> None:
        parts = split_topic(topic, prefix)
        if parts is None:
            return
        station, kind = parts
        self.stats.count(kind)
        try:
            text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            if kind == "status":
                status = StatusPayload.model_validate_json(text)
                self.hub.update_status(station, status)
                self._dirty_stations.add(station)
            elif kind == "player":
                player = PlayerPayload.model_validate_json(text)
                self.hub.update_player(station, player)
                if player.present and player.player is not None:
                    self._spawn(self._resolve_display_name(station, player))
            elif kind == "live":
                live = LivePayload.model_validate_json(text)
                self.hub.update_live(station, live)
                self.frames.add(live)
            elif kind in EVENT_KINDS:
                await asyncio.to_thread(self.spool.append, station, kind, text)
                self._wake.set()
            # Anything else (e.g. our own "cmd") is ignored.
        except (ValidationError, ValueError) as exc:
            self.stats.parse_errors += 1
            self.stats.last_parse_error = f"{topic}: {exc}"[:500]
            log.warning("invalid mqtt payload", topic=topic, error=str(exc)[:300])

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _resolve_display_name(self, station: str, payload: PlayerPayload) -> None:
        card = payload.player
        if card is None or not self.db.is_ready:
            self.hub.set_player_nickname(station, card.name if card else None)
            return
        try:
            async with self.db.session() as session:
                nickname = await players.card_nickname(session, card.uid, card.name)
        except Exception as exc:
            log.debug("card lookup failed", error=repr(exc))
            nickname = card.name
        self.hub.set_player_nickname(station, nickname)

    # ------------------------------------------------------------ event worker

    async def run_worker(self) -> None:
        self.spool.cleanup_temp()
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), RETRY_DELAY_S)
            self._wake.clear()
            if not await self.db.wait_ready(within_s=RETRY_DELAY_S):
                continue
            await self.drain()

    async def drain(self) -> int:
        """Apply all pending events in order. Stops at the first transient error."""
        applied = 0
        for path in self.spool.pending():
            try:
                event = self.spool.load(path)
            except (OSError, ValueError, KeyError) as exc:
                self._fail(path, f"unreadable spool file: {exc!r}")
                continue
            try:
                await self.apply(event)
            except PermanentEventError as exc:
                self._fail(path, str(exc))
                continue
            except _TRANSIENT as exc:
                log.warning("event deferred, database problem", error=repr(exc))
                return applied
            except DBAPIError as exc:
                if exc.connection_invalidated:
                    log.warning("event deferred, connection lost", error=repr(exc))
                    return applied
                if not self._retry_later(path, exc):
                    return applied
                continue
            except Exception as exc:
                if not self._retry_later(path, exc):
                    return applied
                continue
            self.spool.complete(path)
            self._attempts.pop(path.name, None)
            self.stats.events_stored += 1
            applied += 1
        return applied

    def _retry_later(self, path: Any, exc: Exception) -> bool:
        """Count a failed attempt. Returns True if the event was given up."""
        attempts = self._attempts.get(path.name, 0) + 1
        self._attempts[path.name] = attempts
        log.error("event failed", file=path.name, attempt=attempts, error=repr(exc))
        if attempts >= MAX_ATTEMPTS:
            self._fail(path, f"gave up after {attempts} attempts: {exc!r}")
            return True
        return False

    def _fail(self, path: Any, reason: str) -> None:
        self.stats.events_failed += 1
        self.stats.last_event_error = reason[:500]
        self._attempts.pop(path.name, None)
        log.error("event moved to spool/failed", file=path.name, reason=reason[:300])
        self.spool.fail(path, reason)

    async def apply(self, event: SpooledEvent) -> None:
        try:
            if event.kind == "event/game_start":
                start = GameStartPayload.model_validate_json(event.payload)
                game_id = await self._in_tx(games.record_game_start, start)
                self.hub.game_event(event.station, "game_start", {"game_id": start.game_id})
            elif event.kind == "event/cheat":
                cheat = CheatPayload.model_validate_json(event.payload)
                game_id = await self._in_tx(games.record_cheat, cheat)
                self.hub.game_event(
                    event.station, "cheat", {"game_id": cheat.game_id, "cheated": cheat.cheated}
                )
            elif event.kind == "event/game_end":
                end = GameEndPayload.model_validate_json(event.payload)
                game_id = await self._in_tx(games.record_game_end, end)
                self.hub.game_event(
                    event.station,
                    "game_end",
                    {"game_id": end.game_id, "score": end.score, "valid": end.valid},
                )
            else:
                raise PermanentEventError(f"unknown event kind {event.kind!r}")
        except (ValidationError, ValueError) as exc:
            raise PermanentEventError(f"invalid payload: {exc}") from exc
        log.info("event stored", kind=event.kind, station=event.station, game=game_id)

    async def _in_tx(self, fn: Any, payload: Any) -> int:
        async with self.db.session() as session, session.begin():
            result: int = await fn(session, payload)
            return result

    # ------------------------------------------------------------ housekeeping

    async def run_station_sync(self) -> None:
        """Persist station names/status from the hub every few seconds."""
        while True:
            await asyncio.sleep(STATION_SYNC_INTERVAL_S)
            if not self._dirty_stations or not self.db.is_ready:
                continue
            dirty, self._dirty_stations = self._dirty_stations, set()
            try:
                async with self.db.session() as session, session.begin():
                    for station_id in sorted(dirty):
                        state = self.hub.station(station_id)
                        status = state.status.model_dump(mode="json") if state.status else None
                        name = state.status.name if state.status else None
                        seen = state.status_at or datetime.now(UTC)
                        await session.execute(
                            insert(Station)
                            .values(id=station_id, name=name, last_seen_at=seen, last_status=status)
                            .on_conflict_do_nothing(index_elements=[Station.id])
                        )
                        await session.execute(
                            update(Station)
                            .where(Station.id == station_id)
                            .values(
                                last_seen_at=seen,
                                last_status=status,
                                **({"name": name} if name else {}),
                            )
                        )
            except Exception as exc:
                self._dirty_stations |= dirty
                log.warning("station sync failed", error=repr(exc))

    async def run_sweeper(self) -> None:
        while True:
            if await self.db.wait_ready(within_s=None):
                try:
                    async with self.db.session() as session, session.begin():
                        count = await games.abandon_stale_games(session, ABANDON_AFTER)
                    if count:
                        log.info("marked stale live games as abandoned", count=count)
                except Exception as exc:
                    log.warning("sweep failed", error=repr(exc))
            await asyncio.sleep(SWEEP_INTERVAL_S)
