"""Scene engine: OBS overlay scenes, their rounds and live versus numbers.

A *scene* has a fixed OBS URL (``/o/<slug>``), a layout and slots that watch
stations. The engine listens to the LiveHub (synchronously, no extra
latency) and

- binds running games to slots, freezes results on game end
  (``core/rounds.py``), optionally starts the next round automatically;
- forwards every live frame of a slot's station to the scene's overlay
  clients (``frame`` messages, up to 60 Hz);
- recomputes the derived numbers (rank, diff, tetrises behind, pace,
  outcomes) at most every ``STATE_INTERVAL_S`` and pushes them as ``state``
  when they changed;
- persists the round state (``scene_rounds`` / ``scene_round_entries``).

Overlay protocol (``/ws/scene/<slug>``)::

    {"type": "init",  "data": {"state": {...}, "frames": {slot: frame}, "history": {...}}}
    {"type": "state", "data": {...}}
    {"type": "frame", "slot": 0, "data": {...live frame...}}
    {"type": "scene_removed"}
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core import rounds, scoring
from nestris_ltm.core.layouts import LAYOUTS, Layout
from nestris_ltm.core.rounds import Entry, RoundState, Standing
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import Game, Scene, SceneRound, SceneRoundEntry, SceneSlot
from nestris_ltm.live.broadcast import Broadcaster
from nestris_ltm.live.hub import LiveHub

log = structlog.get_logger(__name__)

STATE_INTERVAL_S = 0.1
HISTORY_INTERVAL_MS = 1000  # one score sample per second for the diff graph
HISTORY_MAX = 1800  # 30 minutes
ACTIVE_STATES = ("in_game", "paused", "game_over")


@dataclass
class SlotConfig:
    slot: int
    station_id: str | None = None
    label: str | None = None
    name_override: str | None = None


@dataclass
class SceneRuntime:
    id: int
    slug: str
    name: str
    layout: Layout
    mode: rounds.Mode
    auto_round: bool
    settings: dict[str, Any]
    slots: dict[int, SlotConfig]
    round: RoundState = field(default_factory=RoundState)
    round_id: int | None = None
    channel: Broadcaster = field(default_factory=Broadcaster)
    frames: dict[int, dict[str, Any]] = field(default_factory=dict)
    history: dict[int, deque[tuple[int, int]]] = field(default_factory=dict)
    round_started: float = field(default_factory=time.monotonic)
    last_state: dict[str, Any] | None = None
    dirty: bool = True
    needs_persist: bool = False

    def active_slots(self) -> list[int]:
        return [s for s in range(self.layout.slots) if self._station(s)]

    def _station(self, slot: int) -> str | None:
        cfg = self.slots.get(slot)
        return cfg.station_id if cfg else None


class SceneEngine:
    def __init__(self, db: DatabaseManager, hub: LiveHub) -> None:
        self.db = db
        self.hub = hub
        self.scenes: dict[str, SceneRuntime] = {}
        self._by_station: dict[str, list[tuple[str, int]]] = {}
        self._lock = asyncio.Lock()
        self._loaded = asyncio.Event()
        hub.add_listener(self._on_hub_message)

    # ------------------------------------------------------------ loading

    async def load(self) -> None:
        """(Re)load all scenes, slots and their latest round from the database."""
        async with self._lock, self.db.session() as session:
            rows = (await session.scalars(select(Scene).order_by(Scene.id))).all()
            fresh: dict[str, SceneRuntime] = {}
            for row in rows:
                runtime = self.scenes.get(row.slug)
                layout = LAYOUTS.get(row.layout) or LAYOUTS["1v1"]
                slots = {
                    s.slot: SlotConfig(s.slot, s.station_id, s.label_override, s.name_override)
                    for s in await session.scalars(
                        select(SceneSlot).where(SceneSlot.scene_id == row.id)
                    )
                }
                if runtime is None or runtime.id != row.id:
                    runtime = SceneRuntime(
                        id=row.id,
                        slug=row.slug,
                        name=row.name,
                        layout=layout,
                        mode=row.mode,  # type: ignore[arg-type]
                        auto_round=row.auto_round,
                        settings=dict(row.settings),
                        slots=slots,
                    )
                    await self._load_round(session, runtime)
                else:
                    runtime.name = row.name
                    runtime.layout = layout
                    runtime.mode = row.mode  # type: ignore[assignment]
                    runtime.auto_round = row.auto_round
                    runtime.settings = dict(row.settings)
                    runtime.slots = slots
                runtime.dirty = True
                fresh[row.slug] = runtime
            for slug, old in self.scenes.items():
                if slug not in fresh:
                    old.channel.publish({"type": "scene_removed"})
            self.scenes = fresh
            self._index()
        self._loaded.set()

    async def _load_round(self, session: AsyncSession, runtime: SceneRuntime) -> None:
        row = await session.scalar(
            select(SceneRound)
            .where(SceneRound.scene_id == runtime.id)
            .order_by(SceneRound.number.desc())
            .limit(1)
        )
        if row is None:
            row = SceneRound(scene_id=runtime.id, number=1)
            session.add(row)
            await session.flush()
            await session.commit()
        state = RoundState(number=row.number)
        for e in await session.scalars(
            select(SceneRoundEntry).where(SceneRoundEntry.round_id == row.id)
        ):
            state.entries[e.slot] = Entry(
                slot=e.slot,
                game_id=e.game_external_id,
                player_name=e.player_name,
                score=e.frozen_score,
                lines=e.frozen_lines,
                level=e.frozen_level,
                start_level=e.frozen_start_level,
                finished_at=e.finished_at,
                outcome=e.outcome,  # type: ignore[arg-type]
            )
        runtime.round = state
        runtime.round_id = row.id

    def _index(self) -> None:
        index: dict[str, list[tuple[str, int]]] = {}
        for runtime in self.scenes.values():
            for slot, cfg in runtime.slots.items():
                if cfg.station_id and slot < runtime.layout.slots:
                    index.setdefault(cfg.station_id, []).append((runtime.slug, slot))
        self._by_station = index

    # ------------------------------------------------------------ live input

    def _on_hub_message(self, message: dict[str, Any]) -> None:
        station = message.get("station")
        targets = self._by_station.get(station or "")
        if not targets:
            return
        kind = message.get("type")
        if kind == "live":
            self._on_live(targets, message["data"])
        elif kind == "game_event":
            self._on_game_event(targets, message.get("kind"), message.get("data") or {})
        elif kind == "station":
            for slug, _ in targets:
                if runtime := self.scenes.get(slug):
                    runtime.dirty = True

    def _on_live(self, targets: list[tuple[str, int]], frame: dict[str, Any]) -> None:
        game_id = frame.get("game_id")
        for slug, slot in targets:
            runtime = self.scenes.get(slug)
            if runtime is None:
                continue
            bound = False
            if game_id and frame.get("game_state") in ACTIVE_STATES:
                bound = self._bind(runtime, slot, game_id, frame)
            entry = runtime.round.entry(slot)
            if bound and not entry.finished:
                entry.score = frame.get("score")
                entry.lines = frame.get("lines")
                entry.level = frame.get("level")
                self._sample(runtime, slot, entry.score)
            # Only frames of the bound game (or idle frames on a waiting slot)
            # reach the overlay; a second game on a finished slot stays hidden.
            if bound or entry.game_id is None:
                runtime.frames[slot] = frame
                runtime.channel.publish({"type": "frame", "slot": slot, "data": frame})
            runtime.dirty = True

    def _bind(
        self, runtime: SceneRuntime, slot: int, game_id: str, frame: dict[str, Any] | None
    ) -> bool:
        entry = runtime.round.entry(slot)
        if entry.game_id == game_id:
            return True
        if (
            entry.finished
            and runtime.auto_round
            and runtime.round.all_finished(runtime.active_slots())
        ):
            # Everybody is done and a new game starts: next round.
            self._start_new_round(runtime, reason="auto")
        if not runtime.round.accepts(slot, game_id):
            return False
        entry = runtime.round.entry(slot)
        entry.player_name = self._player_name(runtime, slot, frame)
        runtime.history[slot] = deque(maxlen=HISTORY_MAX)
        runtime.needs_persist = True
        log.info("scene slot bound", scene=runtime.slug, slot=slot, game=game_id)
        return True

    def _on_game_event(
        self, targets: list[tuple[str, int]], kind: str | None, data: dict[str, Any]
    ) -> None:
        game_id = data.get("game_id")
        if not game_id:
            return
        for slug, slot in targets:
            runtime = self.scenes.get(slug)
            if runtime is None:
                continue
            if kind == "game_start":
                if self._bind(runtime, slot, game_id, None):
                    runtime.round.entry(slot).start_level = data.get("start_level")
            elif kind == "game_end":
                done = runtime.round.finish(
                    slot,
                    game_id,
                    score=data.get("score"),
                    lines=data.get("lines"),
                    level=data.get("level"),
                    start_level=data.get("start_level"),
                )
                if done:
                    self._sample(runtime, slot, runtime.round.entry(slot).score, force=True)
                    runtime.needs_persist = True
                    log.info("scene slot finished", scene=slug, slot=slot, game=game_id)
            runtime.dirty = True

    def _sample(
        self, runtime: SceneRuntime, slot: int, score: int | None, *, force: bool = False
    ) -> None:
        if score is None:
            return
        t_ms = int((time.monotonic() - runtime.round_started) * 1000)
        series = runtime.history.setdefault(slot, deque(maxlen=HISTORY_MAX))
        if force or not series or t_ms - series[-1][0] >= HISTORY_INTERVAL_MS:
            series.append((t_ms, score))

    def _player_name(
        self, runtime: SceneRuntime, slot: int, frame: dict[str, Any] | None
    ) -> str | None:
        cfg = runtime.slots.get(slot)
        if cfg and cfg.name_override:
            return cfg.name_override
        if cfg and cfg.station_id:
            station = self.hub.station(cfg.station_id)
            if station.player_nickname:
                return station.player_nickname
            card = (frame or {}).get("player") or {}
            if card.get("name"):
                return str(card["name"])
            if station.player and station.player.player and station.player.player.name:
                return station.player.player.name
        return None

    # ------------------------------------------------------------ rounds

    def _start_new_round(self, runtime: SceneRuntime, *, reason: str) -> None:
        runtime.round = RoundState(number=runtime.round.number + 1)
        runtime.round_id = None  # created on the next persist
        runtime.history = {}
        runtime.frames = {}
        runtime.round_started = time.monotonic()
        runtime.needs_persist = True
        runtime.dirty = True
        log.info(
            "scene round started", scene=runtime.slug, round=runtime.round.number, reason=reason
        )

    async def new_round(self, slug: str) -> int:
        runtime = self._get(slug)
        self._start_new_round(runtime, reason="manual")
        await self._persist(runtime)
        return runtime.round.number

    async def reset_slot(self, slug: str, slot: int) -> None:
        """Let one slot play again in the current round."""
        runtime = self._get(slug)
        runtime.round.unfreeze(slot)
        runtime.history.pop(slot, None)
        runtime.frames.pop(slot, None)
        runtime.needs_persist = True
        runtime.dirty = True
        await self._persist(runtime)

    def _get(self, slug: str) -> SceneRuntime:
        runtime = self.scenes.get(slug)
        if runtime is None:
            raise KeyError(slug)
        return runtime

    # ------------------------------------------------------------ derived state

    def compute_state(self, runtime: SceneRuntime) -> dict[str, Any]:
        state = runtime.round
        layout = runtime.layout
        slots_out: list[dict[str, Any]] = []
        standings: list[Standing] = []
        values: dict[int, dict[str, Any]] = {}

        for slot in range(layout.slots):
            cfg = runtime.slots.get(slot) or SlotConfig(slot)
            entry = state.entries.get(slot)
            frame = runtime.frames.get(slot) or {}
            station = self.hub.station(cfg.station_id) if cfg.station_id else None
            if cfg.station_id is None:
                status = "empty"
            elif entry is None or entry.game_id is None:
                status = "waiting"
            elif entry.finished:
                status = "finished"
            else:
                status = "playing"
            score = entry.score if entry else None
            level = entry.level if entry else None
            name = (
                cfg.name_override
                or (entry.player_name if entry else None)
                or self._player_name(runtime, slot, frame)
                or cfg.label
                or (
                    station.status.name
                    if station and station.status and station.status.name
                    else None
                )
                or cfg.station_id
            )
            values[slot] = {"score": score or 0, "level": level, "status": status}
            if status in ("playing", "finished"):
                standings.append(Standing(slot, score or 0, status == "finished"))
            start_level = entry.start_level if entry and entry.start_level is not None else level
            tetris_rate = frame.get("tetris_rate") if status == "playing" else None
            slots_out.append(
                {
                    "slot": slot,
                    "station_id": cfg.station_id,
                    "label": cfg.label,
                    "name": name,
                    "status": status,
                    "online": bool(station and station.online(datetime.now(UTC))),
                    "score": score,
                    "lines": entry.lines if entry else None,
                    "level": level,
                    "start_level": start_level,
                    "tetris_rate": frame.get("tetris_rate"),
                    "burn": frame.get("burn"),
                    "drought": frame.get("drought"),
                    "max_drought": frame.get("max_drought"),
                    "pieces": frame.get("pieces"),
                    "pace": (
                        scoring.project_score(
                            score or 0, entry.lines or 0, start_level, tetris_rate
                        )
                        if status == "playing" and entry
                        else score
                    ),
                }
            )

        outcomes = rounds.decide_outcomes(runtime.mode, standings)
        if outcomes != {e.slot: e.outcome for e in state.entries.values() if e.outcome}:
            for slot, entry in state.entries.items():
                new = outcomes.get(slot)
                if entry.outcome != new:
                    entry.outcome = new
                    runtime.needs_persist = True

        ranked = sorted(standings, key=lambda s: (-s.score, s.slot))
        rank_of = {s.slot: i + 1 for i, s in enumerate(ranked)}
        leader = ranked[0] if ranked else None
        for out in slots_out:
            slot = out["slot"]
            out["rank"] = rank_of.get(slot)
            out["outcome"] = outcomes.get(slot)
            score = out["score"] or 0
            level = out["level"]
            if leader is not None and out["status"] in ("playing", "finished"):
                out["to_leader"] = _gap_dict(rounds.gap(score, leader.score, level))
            partner = layout.partner(slot)
            if (
                partner is not None
                and values[partner]["status"] in ("playing", "finished")
                and out["status"] in ("playing", "finished")
            ):
                out["vs_partner"] = _gap_dict(rounds.gap(score, values[partner]["score"], level))
            target = rounds.score_to_beat(runtime.mode, standings, slot)
            if target is not None and out["status"] == "playing":
                out["to_advance"] = {"score": target, **_gap_dict(rounds.gap(score, target, level))}

        return {
            "scene": {
                "slug": runtime.slug,
                "name": runtime.name,
                "layout": layout.id,
                "mode": runtime.mode,
                "auto_round": runtime.auto_round,
                "settings": runtime.settings,
                "pairs": [list(p) for p in layout.pairs],
            },
            "round": state.number,
            "complete": state.all_finished(runtime.active_slots()),
            "leader": leader.slot if leader else None,
            "slots": slots_out,
        }

    def snapshot(self, slug: str) -> dict[str, Any]:
        runtime = self._get(slug)
        return {
            "state": self.compute_state(runtime),
            "frames": {str(k): v for k, v in runtime.frames.items()},
            "history": {str(k): list(v) for k, v in runtime.history.items()},
        }

    # ------------------------------------------------------------ loop + persistence

    async def run(self) -> None:
        while True:
            if not self._loaded.is_set():
                if await self.db.wait_ready(within_s=5.0):
                    try:
                        await self.load()
                    except Exception as exc:
                        log.warning("loading scenes failed", error=repr(exc))
                        await asyncio.sleep(5)
                continue
            for runtime in list(self.scenes.values()):
                if runtime.dirty:
                    runtime.dirty = False
                    current = self.compute_state(runtime)
                    if current != runtime.last_state:
                        runtime.last_state = current
                        runtime.channel.publish({"type": "state", "data": current})
                if runtime.needs_persist:
                    try:
                        await self._persist(runtime)
                    except Exception as exc:
                        log.warning(
                            "persisting scene round failed", scene=runtime.slug, error=repr(exc)
                        )
            await asyncio.sleep(STATE_INTERVAL_S)

    async def _persist(self, runtime: SceneRuntime) -> None:
        runtime.needs_persist = False
        async with self.db.session() as session, session.begin():
            if runtime.round_id is None:
                await session.execute(
                    update(SceneRound)
                    .where(SceneRound.scene_id == runtime.id, SceneRound.ended_at.is_(None))
                    .values(ended_at=func.now())
                )
                row = SceneRound(scene_id=runtime.id, number=runtime.round.number)
                session.add(row)
                await session.flush()
                runtime.round_id = row.id
            await session.execute(
                delete(SceneRoundEntry).where(SceneRoundEntry.round_id == runtime.round_id)
            )
            game_ids = {
                e.game_id
                for e in runtime.round.entries.values()
                if e.game_id is not None and e.finished
            }
            known = (
                dict(
                    (
                        await session.execute(
                            select(Game.external_id, Game.id).where(Game.external_id.in_(game_ids))
                        )
                    ).all()
                )
                if game_ids
                else {}
            )
            for entry in runtime.round.entries.values():
                if entry.game_id is None:
                    continue
                session.add(
                    SceneRoundEntry(
                        round_id=runtime.round_id,
                        slot=entry.slot,
                        game_id=known.get(entry.game_id),
                        game_external_id=entry.game_id,
                        player_name=(entry.player_name or "")[:64] or None,
                        frozen_score=entry.score if entry.finished else None,
                        frozen_lines=entry.lines if entry.finished else None,
                        frozen_level=entry.level if entry.finished else None,
                        frozen_start_level=entry.start_level,
                        finished_at=entry.finished_at,
                        outcome=entry.outcome,
                    )
                )

    async def close(self) -> None:
        for runtime in self.scenes.values():
            if runtime.needs_persist:
                with contextlib.suppress(Exception):
                    await self._persist(runtime)


def _gap_dict(g: rounds.Gap) -> dict[str, Any]:
    return {"points": g.points, "tetrises": g.tetrises, "tetrises_needed": g.tetrises_needed}
