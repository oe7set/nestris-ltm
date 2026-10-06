"""Scene engine: OBS overlay scenes, their rounds and live versus numbers.

A *scene* has a fixed OBS URL (``/o/<slug>``), a layout and slots that watch
stations. The engine listens to the LiveHub (synchronously, no extra
latency) and

- binds running games to slots, freezes results on game end
  (``core/rounds.py``), optionally starts the next round automatically;
  every head-to-head pair of a layout (``Layout.pairs``, e.g. both matches
  of ``2x1v1``) plays its own rounds ("groups"), other layouts one group;
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
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core import rounds, scoring
from nestris_ltm.core.layouts import LAYOUTS, Layout
from nestris_ltm.core.rounds import Entry, RoundState, Standing
from nestris_ltm.core.scene_settings import normalize as normalize_settings
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import Game, Scene, SceneRound, SceneRoundEntry, SceneSlot
from nestris_ltm.live.broadcast import Broadcaster
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services import overlay_layouts

if TYPE_CHECKING:
    from nestris_ltm.services.match_lives import MatchLives

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
    # Own layouts: "<uuid>:<version>"; overlays fetch the definition when it changes.
    layout_rev: str | None = None
    # Per group: the current round, its database id (None = not stored yet)
    # and when it started (time axis of the diff graph).
    rounds: dict[int, RoundState] = field(default_factory=dict)
    round_ids: dict[int, int | None] = field(default_factory=dict)
    channel: Broadcaster = field(default_factory=Broadcaster)
    frames: dict[int, dict[str, Any]] = field(default_factory=dict)
    history: dict[int, deque[tuple[int, int]]] = field(default_factory=dict)
    round_started: dict[int, float] = field(default_factory=dict)
    last_state: dict[str, Any] | None = None
    dirty: bool = True
    needs_persist: bool = False

    def active_slots(self) -> list[int]:
        return [s for s in range(self.layout.slots) if self._station(s)]

    # ---- round groups: one per head-to-head pair, else one for all slots

    def groups(self) -> list[int]:
        return list(range(len(self.layout.pairs))) or [0]

    def group_of(self, slot: int) -> int:
        for index, pair in enumerate(self.layout.pairs):
            if slot in pair:
                return index
        return 0

    def group_slots(self, group: int) -> list[int]:
        if self.layout.pairs and group < len(self.layout.pairs):
            return list(self.layout.pairs[group])
        return list(range(self.layout.slots))

    def active_group_slots(self, group: int) -> list[int]:
        return [s for s in self.group_slots(group) if self._station(s)]

    def group_round(self, group: int) -> RoundState:
        return self.rounds.setdefault(group, RoundState())

    def round_of(self, slot: int) -> RoundState:
        return self.group_round(self.group_of(slot))

    @property
    def round(self) -> RoundState:
        """The round of group 0 (the only one of single-group layouts)."""
        return self.group_round(0)

    def started(self, group: int) -> float:
        return self.round_started.setdefault(group, time.monotonic())

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
        # Hearts of the bracket match a pair shows (set by the runtime).
        self.lives: MatchLives | None = None
        self._background: set[asyncio.Task[Any]] = set()
        hub.add_listener(self._on_hub_message)

    def mark_all_dirty(self) -> None:
        """Recompute every scene's state (e.g. hearts changed)."""
        for runtime in self.scenes.values():
            runtime.dirty = True

    # ------------------------------------------------------------ loading

    async def load(self) -> None:
        """(Re)load all scenes, slots and their latest round from the database."""
        async with self._lock, self.db.session() as session:
            rows = (await session.scalars(select(Scene).order_by(Scene.id))).all()
            known = await overlay_layouts.all_layouts(session)
            revs = await overlay_layouts.revisions(session)
            fresh: dict[str, SceneRuntime] = {}
            for row in rows:
                runtime = self.scenes.get(row.slug)
                layout = known.get(row.layout)
                if layout is None:
                    log.warning(
                        "scene layout missing, showing 1v1", scene=row.slug, layout=row.layout
                    )
                    layout = LAYOUTS["1v1"]
                settings, dropped = normalize_settings(row.settings)
                if dropped:
                    log.warning("scene settings ignored", scene=row.slug, keys=dropped)
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
                        settings=settings.stored(),
                        slots=slots,
                        layout_rev=revs.get(row.layout),
                    )
                    await self._load_round(session, runtime)
                else:
                    relayout = runtime.layout.id != layout.id
                    runtime.name = row.name
                    runtime.layout = layout
                    runtime.mode = row.mode  # type: ignore[assignment]
                    runtime.auto_round = row.auto_round
                    runtime.settings = settings.stored()
                    runtime.layout_rev = revs.get(row.layout)
                    runtime.slots = slots
                    if relayout:
                        await self._load_round(session, runtime)
                runtime.dirty = True
                fresh[row.slug] = runtime
            for slug, old in self.scenes.items():
                if slug not in fresh:
                    old.channel.publish({"type": "scene_removed"})
            self.scenes = fresh
            self._index()
        self._loaded.set()

    async def _load_round(self, session: AsyncSession, runtime: SceneRuntime) -> None:
        runtime.rounds, runtime.round_ids = {}, {}
        for group in runtime.groups():
            await self._load_group_round(session, runtime, group)

    async def _load_group_round(
        self, session: AsyncSession, runtime: SceneRuntime, group: int
    ) -> None:
        row = await session.scalar(
            select(SceneRound)
            .where(SceneRound.scene_id == runtime.id, SceneRound.group_index == group)
            .order_by(SceneRound.number.desc())
            .limit(1)
        )
        if row is None:
            row = SceneRound(scene_id=runtime.id, group_index=group, number=1)
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
        runtime.rounds[group] = state
        runtime.round_ids[group] = row.id

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
            entry = runtime.round_of(slot).entry(slot)
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
        group = runtime.group_of(slot)
        entry = runtime.group_round(group).entry(slot)
        if entry.game_id == game_id:
            return True
        if (
            entry.finished
            and runtime.auto_round
            and runtime.group_round(group).all_finished(runtime.active_group_slots(group))
        ):
            # Everybody of this group is done and a new game starts: next round.
            self._start_new_round(runtime, group, reason="auto")
        if not runtime.group_round(group).accepts(slot, game_id):
            return False
        entry = runtime.group_round(group).entry(slot)
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
            rnd = runtime.round_of(slot)
            if kind == "game_start":
                if self._bind(runtime, slot, game_id, None):
                    runtime.round_of(slot).entry(slot).start_level = data.get("start_level")
            elif kind == "game_end":
                done = rnd.finish(
                    slot,
                    game_id,
                    score=data.get("score"),
                    lines=data.get("lines"),
                    level=data.get("level"),
                    start_level=data.get("start_level"),
                )
                if done:
                    self._sample(runtime, slot, rnd.entry(slot).score, force=True)
                    runtime.needs_persist = True
                    log.info("scene slot finished", scene=slug, slot=slot, game=game_id)
                    group = runtime.group_of(slot)
                    if rnd.all_finished(runtime.active_group_slots(group)):
                        self._round_complete(runtime, group)
            runtime.dirty = True

    def _sample(
        self, runtime: SceneRuntime, slot: int, score: int | None, *, force: bool = False
    ) -> None:
        if score is None:
            return
        t_ms = int((time.monotonic() - runtime.started(runtime.group_of(slot))) * 1000)
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

    def _start_new_round(self, runtime: SceneRuntime, group: int, *, reason: str) -> None:
        number = runtime.group_round(group).number + 1
        runtime.rounds[group] = RoundState(number=number)
        runtime.round_ids[group] = None  # created on the next persist
        for slot in runtime.group_slots(group):
            runtime.history.pop(slot, None)
            runtime.frames.pop(slot, None)
        runtime.round_started[group] = time.monotonic()
        runtime.needs_persist = True
        runtime.dirty = True
        log.info(
            "scene round started", scene=runtime.slug, group=group, round=number, reason=reason
        )

    def _round_complete(self, runtime: SceneRuntime, group: int) -> None:
        """Every slot of a group finished: the hearts may take the loser's heart."""
        if self.lives is None or not runtime.layout.pairs:
            return
        rnd = runtime.group_round(group)
        scores = {slot: rnd.entry(slot).score for slot in runtime.group_slots(group)}
        task = asyncio.get_running_loop().create_task(
            self.lives.round_complete(runtime, group, rnd.number, scores)
        )
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def new_round(self, slug: str, group: int | None = None) -> dict[int, int]:
        """Next round for one group or (``None``) all; returns {group: round}."""
        runtime = self._get(slug)
        groups = runtime.groups() if group is None else [group]
        if any(g not in runtime.groups() for g in groups):
            raise ValueError(f"the layout has no group {group}")
        for g in groups:
            self._start_new_round(runtime, g, reason="manual")
        await self._persist(runtime)
        return {g: runtime.group_round(g).number for g in groups}

    async def reset_slot(self, slug: str, slot: int) -> None:
        """Let one slot play again in the current round."""
        runtime = self._get(slug)
        runtime.round_of(slot).unfreeze(slot)
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
        layout = runtime.layout
        slots_out: list[dict[str, Any]] = []
        standings_by_group: dict[int, list[Standing]] = {g: [] for g in runtime.groups()}
        values: dict[int, dict[str, Any]] = {}

        for slot in range(layout.slots):
            cfg = runtime.slots.get(slot) or SlotConfig(slot)
            group = runtime.group_of(slot)
            entry = runtime.group_round(group).entries.get(slot)
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
                standings_by_group[group].append(Standing(slot, score or 0, status == "finished"))
            start_level = entry.start_level if entry and entry.start_level is not None else level
            tetris_rate = frame.get("tetris_rate") if status == "playing" else None
            slots_out.append(
                {
                    "slot": slot,
                    "group": group,
                    "round": runtime.group_round(group).number,
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

        outcomes: dict[int, rounds.Outcome] = {}
        rank_of: dict[int, int] = {}
        leaders: dict[int, Standing] = {}
        for group, standings in standings_by_group.items():
            decided = rounds.decide_outcomes(runtime.mode, standings)
            outcomes.update(decided)
            for slot, entry in runtime.group_round(group).entries.items():
                if entry.outcome != decided.get(slot):
                    entry.outcome = decided.get(slot)
                    runtime.needs_persist = True
            ranked = sorted(standings, key=lambda s: (-s.score, s.slot))
            rank_of.update({s.slot: i + 1 for i, s in enumerate(ranked)})
            if ranked:
                leaders[group] = ranked[0]

        for out in slots_out:
            slot = out["slot"]
            standings = standings_by_group[out["group"]]
            leader = leaders.get(out["group"])
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

        groups_out = [
            {
                "group": g,
                "slots": runtime.group_slots(g),
                "round": runtime.group_round(g).number,
                "complete": runtime.group_round(g).all_finished(runtime.active_group_slots(g)),
            }
            for g in runtime.groups()
        ]

        # Hearts: the bracket match bound to each head-to-head pair.
        matches: list[dict[str, Any]] = []
        if self.lives is not None:
            for index in range(len(layout.pairs)):
                info = self.lives.pair_info(runtime, index)
                if info is None:
                    continue
                matches.append({k: v for k, v in info.items() if k != "slots"})
                for slot, side in info["slots"].items():
                    if slot < len(slots_out):
                        slots_out[slot]["lives"] = {
                            "current": side["lives"],
                            "max": info["max_lives"],
                        }
                        slots_out[slot]["match_result"] = side["result"]

        return {
            "matches": matches,
            "scene": {
                "slug": runtime.slug,
                "name": runtime.name,
                "layout": layout.id,
                "mode": runtime.mode,
                "auto_round": runtime.auto_round,
                "settings": runtime.settings,
                "layout_rev": runtime.layout_rev,
                "pairs": [list(p) for p in layout.pairs],
            },
            "round": runtime.round.number,
            "groups": groups_out,
            "complete": all(g["complete"] for g in groups_out),
            "leader": leaders[0].slot if 0 in leaders else None,
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
            game_ids = {
                e.game_id
                for rnd in runtime.rounds.values()
                for e in rnd.entries.values()
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
            for group in runtime.groups():
                await self._persist_group(session, runtime, group, known)

    async def _persist_group(
        self, session: AsyncSession, runtime: SceneRuntime, group: int, known: dict[Any, int]
    ) -> None:
        rnd = runtime.group_round(group)
        round_id = runtime.round_ids.get(group)
        if round_id is None:
            await session.execute(
                update(SceneRound)
                .where(
                    SceneRound.scene_id == runtime.id,
                    SceneRound.group_index == group,
                    SceneRound.ended_at.is_(None),
                )
                .values(ended_at=func.now())
            )
            row = SceneRound(scene_id=runtime.id, group_index=group, number=rnd.number)
            session.add(row)
            await session.flush()
            round_id = runtime.round_ids[group] = row.id
        await session.execute(delete(SceneRoundEntry).where(SceneRoundEntry.round_id == round_id))
        for entry in rnd.entries.values():
            if entry.game_id is None:
                continue
            session.add(
                SceneRoundEntry(
                    round_id=round_id,
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
