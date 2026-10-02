"""Batches live frames per game and writes them to ``game_frames``.

Live frames arrive at up to 60 Hz per station (one per NES frame). Writing each one would
cost a round trip per message, so frames are collected in memory and
flushed about once per second. Frames can arrive before the game row exists
(``live`` carries the game id before ``event/game_start`` is processed);
they wait here until the row shows up or they get too old.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core import playfield
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import Game, GameFrame
from nestris_ltm.ingest.payloads import LivePayload

log = structlog.get_logger(__name__)

MAX_WAIT_FOR_GAME_S = 120.0
MAX_PENDING_PER_GAME = 60 * 60 * 15  # 15 minutes at 60 Hz (database outage buffer)
# Rows per INSERT; keeps the bind parameter count far below PostgreSQL's limit.
INSERT_CHUNK = 2000
GAME_CACHE_SIZE = 64


@dataclass
class _Pending:
    frames: list[LivePayload] = field(default_factory=list)
    first_seen: float = field(default_factory=time.monotonic)


@dataclass
class _GameRef:
    id: int
    started_at: datetime
    next_seq: int


class FrameBuffer:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._pending: dict[str, _Pending] = {}
        self._games: OrderedDict[str, _GameRef] = OrderedDict()
        self._lock = asyncio.Lock()
        self.frames_written = 0
        self.frames_dropped = 0

    def add(self, payload: LivePayload) -> None:
        if payload.game_id is None:
            return
        pending = self._pending.setdefault(payload.game_id, _Pending())
        pending.frames.append(payload)
        if len(pending.frames) > MAX_PENDING_PER_GAME:
            # Drop the oldest frames in one go (a list pop(0) per frame is O(n)).
            excess = len(pending.frames) - MAX_PENDING_PER_GAME
            del pending.frames[:excess]
            self.frames_dropped += excess

    @property
    def pending_count(self) -> int:
        return sum(len(p.frames) for p in self._pending.values())

    async def run(self, interval_s: float = 1.0) -> None:
        while True:
            await asyncio.sleep(interval_s)
            if not self._db.is_ready or not self._pending:
                continue
            try:
                await self.flush()
            except Exception as exc:
                # Frames stay pending and are retried with the next flush.
                log.warning("frame flush failed", error=repr(exc))

    async def flush(self) -> int:
        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> int:
        # Take the frames out first: frames arriving while we await the
        # database land in fresh lists and are kept for the next flush.
        batches = {gid: p.frames for gid, p in self._pending.items() if p.frames}
        for gid in batches:
            self._pending[gid].frames = []
        try:
            written = await self._write(batches)
        except BaseException:
            # Nothing was committed: put the frames back in front and forget
            # cached sequence numbers so the next attempt re-reads them.
            for gid, frames in batches.items():
                pending = self._pending.setdefault(gid, _Pending())
                pending.frames[:0] = frames
                self._games.pop(gid, None)
            raise
        for gid in list(self._pending):
            if not self._pending[gid].frames:
                del self._pending[gid]
        self.frames_written += written
        return written

    async def _write(self, batches: dict[str, list[LivePayload]]) -> int:
        written = 0
        async with self._db.session() as session:
            for external_id, frames in batches.items():
                ref = self._games.get(external_id)
                if ref is None:
                    ref = await self._load_ref(session, external_id)
                if ref is None:
                    pending = self._pending[external_id]
                    if time.monotonic() - pending.first_seen > MAX_WAIT_FOR_GAME_S:
                        self.frames_dropped += len(frames) + len(pending.frames)
                        del self._pending[external_id]
                        log.info("dropping frames of unknown game", game_id=external_id)
                    else:
                        pending.frames[:0] = frames  # wait for the game row
                    continue

                rows = []
                for frame in frames:
                    t_ms = int((frame.ts - ref.started_at).total_seconds() * 1000)
                    rows.append(
                        {
                            "game_id": ref.id,
                            "seq": ref.next_seq,
                            "t_ms": max(t_ms, 0),
                            "game_state": frame.game_state[:16],
                            "score": frame.score,
                            "lines": frame.lines,
                            "level": frame.level,
                            "next_piece": frame.next_piece[:1] if frame.next_piece else None,
                            "playfield": (
                                playfield.pack_rows(frame.playfield) if frame.playfield else None
                            ),
                        }
                    )
                    ref.next_seq += 1
                for i in range(0, len(rows), INSERT_CHUNK):
                    chunk = rows[i : i + INSERT_CHUNK]
                    await session.execute(insert(GameFrame).values(chunk).on_conflict_do_nothing())
                written += len(rows)
            await session.commit()
        return written

    async def _load_ref(self, session: AsyncSession, external_id: str) -> _GameRef | None:
        row = (
            await session.execute(
                select(Game.id, Game.started_at).where(Game.external_id == external_id)
            )
        ).one_or_none()
        if row is None:
            return None
        max_seq = (
            await session.execute(
                select(func.max(GameFrame.seq)).where(GameFrame.game_id == row.id)
            )
        ).scalar_one_or_none()
        ref = _GameRef(row.id, row.started_at, (max_seq or 0) + 1)
        self._remember(external_id, ref)
        return ref

    def _remember(self, external_id: str, ref: _GameRef) -> None:
        self._games[external_id] = ref
        self._games.move_to_end(external_id)
        while len(self._games) > GAME_CACHE_SIZE:
            self._games.popitem(last=False)
