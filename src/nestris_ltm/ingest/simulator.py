"""Station simulator: replays NGF recordings as a ``nestris-station`` over MQTT.

For development and rehearsals without capture hardware:

    nestris-ltm simulate game.ngf --station station-1 --name Erv --uid A1B2C3D4

It publishes the same topics and payload shapes as the real station
(``status``, ``player``, ``live``, ``event/game_start``, ``event/game_end``),
paced by the recorded timestamps divided by ``speed``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiomqtt
import structlog

from nestris_ltm import __version__
from nestris_ltm.config import MqttSettings
from nestris_ltm.core import playfield
from nestris_ltm.core.ngf import NgfFrame, iter_frames, split_games

log = structlog.get_logger(__name__)

MIN_GAME_FRAMES = 120  # like the station's session.min_game_frames
LIVE_INTERVAL_MS = 100  # 10 Hz, the station default
COUNT_CONFIRM_FRAMES = 3
I_PIECE = 6  # index of I in the T J Z O S L I counter order


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class GameTracker:
    """Derives the station's per-game statistics from NGF frames."""

    start_level: int | None = None
    score: int | None = None
    lines: int | None = None
    level: int | None = None
    clears: dict[str, int] = field(
        default_factory=lambda: {"single": 0, "double": 0, "triple": 0, "tetris": 0}
    )
    burn: int = 0
    pieces: int = 0
    drought: int = 0
    max_drought: int = 0
    _candidate: list[int | None] = field(default_factory=lambda: [None] * 7)
    _stable: list[int] = field(default_factory=lambda: [0] * 7)
    _confirmed: list[int | None] = field(default_factory=lambda: [None] * 7)

    def update(self, frame: NgfFrame) -> None:
        if self.start_level is None and frame.level is not None:
            self.start_level = frame.level
        if frame.lines is not None:
            if self.lines is not None and 0 < frame.lines - self.lines <= 4:
                kind = ("single", "double", "triple", "tetris")[frame.lines - self.lines - 1]
                self.clears[kind] += 1
                if kind != "tetris":
                    self.burn += frame.lines - self.lines
            self.lines = frame.lines
        if frame.score is not None:
            self.score = frame.score
        if frame.level is not None:
            self.level = frame.level

        # Piece counters are OCR'd and flicker (2 -> 9 -> 2). A counter value
        # only counts once it held for COUNT_CONFIRM_FRAMES and is a small
        # forward step from the confirmed value.
        for i, value in enumerate(frame.counts):
            if value is None:
                continue
            if value != self._candidate[i]:
                self._candidate[i], self._stable[i] = value, 1
                continue
            self._stable[i] += 1
            if self._stable[i] != COUNT_CONFIRM_FRAMES:
                continue
            confirmed = self._confirmed[i]
            if confirmed is None:
                self._confirmed[i] = value
            elif 0 < value - confirmed <= 2:
                step = value - confirmed
                self._confirmed[i] = value
                self.pieces += step
                if i == I_PIECE:
                    self.drought = 0
                else:
                    self.drought += step
                    self.max_drought = max(self.max_drought, self.drought)

    @property
    def tetris_rate(self) -> float | None:
        if not self.lines:
            return None
        return round(self.clears["tetris"] * 4 / self.lines, 4)


class StationSimulator:
    def __init__(
        self,
        settings: MqttSettings,
        station: str,
        *,
        card_name: str | None = None,
        card_uid: str | None = None,
        speed: float = 1.0,
    ) -> None:
        self.settings = settings
        self.station = station
        self.card_name = card_name
        self.card_uid = card_uid or (f"{zlib.crc32(station.encode()):08X}" if card_name else None)
        self.speed = max(speed, 0.01)
        self.base = f"{settings.topic_prefix.rstrip('/')}/{station}"
        self._started = time.monotonic()
        self._game_state = "title"
        self._game_id: str | None = None

    def _player(self) -> dict[str, Any] | None:
        if self.card_uid is None:
            return None
        return {"uid": self.card_uid, "name": self.card_name}

    def _status(self, state: str = "online") -> dict[str, Any]:
        return {
            "state": state,
            "station": self.station,
            "name": f"Simulator {self.station}",
            "version": f"sim-{__version__}",
            "capture": "ok",
            "capture_detail": "ngf replay",
            "lock": "locked",
            "game_state": self._game_state,
            "rfid": "ok" if self.card_uid else "disabled",
            "game_id": self._game_id,
            "fps": 60.0,
            "dropped_frames": 0,
            "uptime_s": int(time.monotonic() - self._started),
            "ts": _stamp(datetime.now(UTC)),
        }

    async def _pub(
        self,
        client: aiomqtt.Client,
        topic: str,
        payload: dict[str, Any],
        *,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        await client.publish(
            f"{self.base}/{topic}",
            json.dumps(payload, separators=(",", ":")),
            qos=qos,
            retain=retain,
        )

    async def run(self, games: Sequence[Sequence[NgfFrame]], *, loop: bool = False) -> int:
        """Play the games; returns the number of games published."""
        s = self.settings
        will = aiomqtt.Will(
            f"{self.base}/status",
            json.dumps({"state": "offline", "station": self.station, "ts": None}),
            qos=1,
            retain=True,
        )
        published = 0
        async with aiomqtt.Client(
            s.host,
            s.port,
            username=s.username,
            password=s.password.get_secret_value() if s.password else None,
            identifier=f"nestris-sim-{self.station}",
            will=will,
        ) as client:
            await self._pub(client, "status", self._status(), qos=1, retain=True)
            await self._pub(
                client,
                "player",
                {
                    "present": self.card_uid is not None,
                    "player": self._player(),
                    "rfid": "ok",
                    "ts": _stamp(datetime.now(UTC)),
                },
                qos=1,
                retain=True,
            )
            heartbeat = asyncio.create_task(self._heartbeat(client))
            try:
                while True:
                    for frames in games:
                        await self._play(client, frames)
                        published += 1
                        await asyncio.sleep(2.0 / self.speed)
                    if not loop:
                        break
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
                offline = {
                    "state": "offline",
                    "station": self.station,
                    "ts": _stamp(datetime.now(UTC)),
                }
                await self._pub(client, "status", offline, qos=1, retain=True)
        return published

    async def _heartbeat(self, client: aiomqtt.Client) -> None:
        while True:
            await asyncio.sleep(10)
            await self._pub(client, "status", self._status(), qos=1, retain=True)

    async def _play(self, client: aiomqtt.Client, frames: Sequence[NgfFrame]) -> None:
        started_at = datetime.now(UTC)
        t0 = time.monotonic()
        self._game_id = f"{self.station}-{int(started_at.timestamp() * 1000)}"
        self._game_state = "in_game"
        tracker = GameTracker()
        tracker.update(frames[0])
        log.info("simulating game", station=self.station, game=self._game_id, frames=len(frames))

        await self._pub(
            client,
            "event/game_start",
            {
                "game_id": self._game_id,
                "station": self.station,
                "player": self._player(),
                "started_at": _stamp(started_at),
                "start_level": tracker.start_level,
            },
            qos=1,
        )
        await self._pub(client, "status", self._status(), qos=1, retain=True)

        base_ms = frames[0].ctime_ms
        last_live = -LIVE_INTERVAL_MS
        for frame in frames:
            tracker.update(frame)
            rel_ms = frame.ctime_ms - base_ms
            if rel_ms - last_live < LIVE_INTERVAL_MS and frame is not frames[-1]:
                continue
            last_live = rel_ms
            delay = rel_ms / 1000 / self.speed - (time.monotonic() - t0)
            if delay > 0:
                await asyncio.sleep(delay)
            await self._pub(client, "live", self._live(frame, tracker, started_at, rel_ms))

        ended_at = started_at + timedelta(milliseconds=frames[-1].ctime_ms - base_ms)
        duration = (ended_at - started_at).total_seconds()
        await self._pub(
            client,
            "event/game_end",
            {
                "schema": 1,
                "game_id": self._game_id,
                "station": self.station,
                "player": self._player(),
                "started_at": _stamp(started_at),
                "ended_at": _stamp(ended_at),
                "duration_s": round(duration, 3),
                "active_seconds": round(duration, 3),
                "end_reason": "game_over",
                "start_level": tracker.start_level,
                "end_level": tracker.level,
                "score": tracker.score,
                "lines": tracker.lines,
                "clears": tracker.clears,
                "tetris_rate": tracker.tetris_rate,
                "burn": tracker.burn,
                "max_drought": tracker.max_drought,
                "pieces": tracker.pieces,
                "pps": round(tracker.pieces / duration, 4) if duration > 0 else None,
                "cheated": 0,
                "cheat_points": 0,
                "valid": True,
                "validation": {"issues": [], "metrics": {"frames": len(frames), "simulated": True}},
            },
            qos=1,
        )
        self._game_state = "game_over"
        self._game_id = None
        await self._pub(client, "status", self._status(), qos=1, retain=True)

    def _live(
        self, frame: NgfFrame, tracker: GameTracker, started_at: datetime, rel_ms: int
    ) -> dict[str, Any]:
        return {
            "game_id": self._game_id,
            "player": self._player(),
            "game_state": "in_game",
            "score": frame.score,
            "lines": frame.lines,
            "level": frame.level,
            "next_piece": frame.preview,
            "tetris_rate": tracker.tetris_rate,
            "burn": tracker.burn,
            "drought": tracker.drought,
            "max_drought": tracker.max_drought,
            "pps": None,
            "pieces": tracker.pieces,
            "cheated": 0,
            "confidence": 1.0,
            "playfield": playfield.rows_from_cells(frame.field),
            "ts": _stamp(started_at + timedelta(milliseconds=rel_ms)),
        }


def load_games(paths: Iterable[Path]) -> list[list[NgfFrame]]:
    games: list[list[NgfFrame]] = []
    for path in paths:
        for game in split_games(list(iter_frames(path.read_bytes()))):
            if len(game) >= MIN_GAME_FRAMES:
                games.append(game)
    return games
