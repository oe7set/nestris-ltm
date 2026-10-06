"""Hearts of the 1-vs-1 bracket matches and which match a scene pair shows.

Once the bracket is fixed, every real match is a series (``core/lives.py``):
both players start with the tournament's ``default_lives`` (per match
``match_series.max_lives``), the loser of a round loses a heart. At zero
hearts the opponent is set as the bracket winner through
``TournamentService.mutate`` (so the bracket, the kiosk and the tournament
console update as for a click); giving the heart back clears that winner
again as long as it came from the hearts.

The hearts are folded from ``match_life_events`` (kept in memory for the
overlays, which read them at up to 10 Hz). Fixing, resetting or unseeding the
bracket deletes the events (the audit log keeps them).

Scene pairs (``Layout.pairs``) are bound to a match manually or, with
``auto_bind``, as soon as the two stations of a pair hold the cards of the
two players of an open match (``scene_pair_matches``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from nestris_ltm.core import lives as core
from nestris_ltm.core.bracket import Bracket, Match, MatchKind, find_match
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import MatchLifeEvent, MatchSeries, ScenePairMatch, Tournament
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services import audit
from nestris_ltm.services.players import normalize_nickname

if TYPE_CHECKING:
    from nestris_ltm.services.scenes import SceneEngine, SceneRuntime
    from nestris_ltm.services.tournament import TournamentService

log = structlog.get_logger(__name__)

TICK_S = 1.0
THIRD_PLACE_NAME = "Spiel um Platz 3"


@dataclass
class _Event:
    id: int
    match_id: str
    player_id: int
    kind: core.Kind
    value: int | None
    source: str
    actor: str | None
    created_at: datetime
    undone: bool

    def life(self) -> core.LifeEvent:
        return core.LifeEvent(self.player_id, self.kind, self.value, self.undone)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "player_id": self.player_id,
            "kind": self.kind,
            "value": self.value,
            "source": self.source,
            "actor": self.actor,
            "created_at": self.created_at.isoformat(),
            "undone": self.undone,
        }


@dataclass
class Binding:
    scene_id: int
    pair: int
    match_id: str
    bound_by: str  # manual | auto


@dataclass
class Settings:
    default_lives: int = 2
    auto_bind: bool = True
    auto_deduct: bool = False


class MatchLives:
    def __init__(self, db: DatabaseManager, tournament: TournamentService, hub: LiveHub) -> None:
        self.db = db
        self.tournament = tournament
        self.hub = hub
        self.scenes: SceneEngine | None = None  # set by the runtime
        self.settings = Settings()
        self._tournament_id: int | None = None
        self._loaded = False
        self._events: list[_Event] = []
        self._max: dict[str, int | None] = {}
        self._decided_by_lives: set[str] = set()
        self.bindings: dict[tuple[int, int], Binding] = {}
        # Last known side of each slot per bound pair (cards get removed).
        self._sides: dict[tuple[int, int], dict[int, int]] = {}
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        tournament.on_reset.append(self._forget)

    # ------------------------------------------------------------ loading

    def add_listener(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _changed(self) -> None:
        for fn in self._listeners:
            try:
                fn()
            except Exception:  # pragma: no cover - a listener must not break us
                log.exception("lives listener failed")

    def _forget(self) -> None:
        """The bracket was fixed / reset / unseeded: hearts start over."""
        self._events = []
        self._max = {}
        self._decided_by_lives = set()
        self.bindings = {}
        self._sides = {}
        self._changed()

    async def _ensure_loaded(self) -> None:
        tid = self.tournament.tournament_id
        if self._loaded and tid == self._tournament_id:
            return
        self._tournament_id = tid
        self._forget()
        self.settings = Settings()
        if tid is not None:
            async with self.db.session() as session:
                row = await session.get(Tournament, tid)
                if row is not None:
                    self.settings = Settings(row.default_lives, row.auto_bind, row.auto_deduct)
                for e in await session.scalars(
                    select(MatchLifeEvent)
                    .where(MatchLifeEvent.tournament_id == tid)
                    .order_by(MatchLifeEvent.id)
                ):
                    self._events.append(_event(e))
                for s in await session.scalars(
                    select(MatchSeries).where(MatchSeries.tournament_id == tid)
                ):
                    self._max[s.match_id] = s.max_lives
                    if s.decided_by_lives:
                        self._decided_by_lives.add(s.match_id)
                for b in await session.scalars(
                    select(ScenePairMatch).where(ScenePairMatch.tournament_id == tid)
                ):
                    self.bindings[(b.scene_id, b.pair)] = Binding(
                        b.scene_id, b.pair, b.match_id, b.bound_by
                    )
        self._loaded = True
        self._changed()

    async def run(self) -> None:
        """Follow the active tournament and bind scene pairs automatically."""
        while True:
            try:
                if self.db.is_ready:
                    await self._ensure_loaded()
                    await self.auto_bind()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("hearts tick failed", error=repr(exc))
            await asyncio.sleep(TICK_S)

    # ------------------------------------------------------------ views

    def _bracket(self) -> Bracket | None:
        state = self.tournament.state
        return state.bracket() if state.is_seeded else None

    def max_lives(self, match_id: str) -> int:
        return self._max.get(match_id) or self.settings.default_lives

    def lives_of(self, match: Match) -> dict[int, int]:
        players = [p.user_id for p in (match.player1, match.player2) if p is not None]
        events = (e.life() for e in self._events if e.match_id == match.match_id)
        return core.fold(events, self.max_lives(match.match_id), players)

    def view(self, match: Match, bracket: Bracket) -> dict[str, Any]:
        lives = self.lives_of(match)
        winner = match.effective_winner
        return {
            "match_id": match.match_id,
            "round": match.round,
            "round_name": _round_name(bracket, match),
            "max_lives": self.max_lives(match.match_id),
            "custom_max": self._max.get(match.match_id) is not None,
            "players": [
                {
                    "id": p.user_id,
                    "nickname": p.nickname,
                    "seed": p.seed,
                    "lives": lives.get(p.user_id),
                }
                for p in (match.player1, match.player2)
                if p is not None
            ],
            "winner_id": winner.user_id if winner else None,
            "decided_by_lives": match.match_id in self._decided_by_lives,
            "events": [e.as_dict() for e in self._events if e.match_id == match.match_id],
        }

    def match_view(self, match_id: str) -> dict[str, Any] | None:
        bracket = self._bracket()
        match = find_match(bracket, match_id) if bracket else None
        return self.view(match, bracket) if match and bracket else None

    def matches(self) -> list[dict[str, Any]]:
        """Every contested match of the fixed bracket, open ones first."""
        bracket = self._bracket()
        if bracket is None:
            return []
        out = [
            self.view(m, bracket)
            for m in _all_matches(bracket)
            if m.kind == MatchKind.REAL and not m.hidden
        ]
        bound = {b.match_id for b in self.bindings.values()}
        for item in out:
            item["bound"] = [
                {"scene_id": b.scene_id, "pair": b.pair, "bound_by": b.bound_by}
                for b in self.bindings.values()
                if b.match_id == item["match_id"]
            ]
        out.sort(key=lambda m: (m["winner_id"] is not None, m["match_id"] not in bound, m["round"]))
        return out

    async def snapshot(self) -> dict[str, Any]:
        await self._ensure_loaded()
        return self.state()

    def state(self) -> dict[str, Any]:
        return {
            "seeded": self.tournament.state.is_seeded,
            "settings": {
                "default_lives": self.settings.default_lives,
                "auto_bind": self.settings.auto_bind,
                "auto_deduct": self.settings.auto_deduct,
            },
            "matches": self.matches(),
        }

    # ------------------------------------------------------------ changing hearts

    async def apply(
        self,
        match_id: str,
        player_id: int,
        kind: core.Kind,
        value: int | None = None,
        *,
        source: core.Source = "admin",
        actor: str = "admin",
        scene: tuple[str, int, int] | None = None,  # (slug, round, pair) of an auto deduction
    ) -> dict[str, Any]:
        async with self._lock:
            await self._ensure_loaded()
            bracket = self._bracket()
            if bracket is None or self._tournament_id is None:
                raise ValueError("fix the bracket before playing for hearts")
            match = find_match(bracket, match_id)
            if match is None or match.kind != MatchKind.REAL:
                raise ValueError(f"{match_id} is not a match between two players")
            ids = {p.user_id for p in (match.player1, match.player2) if p is not None}
            if player_id not in ids:
                raise ValueError("player is not part of this match")
            if kind == "set":
                if value is None or not 0 <= value <= self.max_lives(match_id):
                    raise ValueError(f"value must be 0..{self.max_lives(match_id)}")
            else:
                value = None
            before = self.lives_of(match)
            async with self.db.session() as session, session.begin():
                row = MatchLifeEvent(
                    tournament_id=self._tournament_id,
                    match_id=match_id,
                    player_id=player_id,
                    kind=kind,
                    value=value,
                    source=source,
                    actor=actor[:64],
                    scene_slug=scene[0] if scene else None,
                    scene_round=scene[1] if scene else None,
                    pair=scene[2] if scene else None,
                )
                session.add(row)
                await session.flush()
                self._events.append(_event(row))
                await audit.record(
                    session, actor=actor, action="lives", entity="match", entity_id=0,
                    before={"match_id": match_id, "lives": _str_keys(before)},
                    after={"match_id": match_id, "player_id": player_id, "kind": kind,
                           "value": value, "lives": _str_keys(self.lives_of(match))},
                )  # fmt: skip
            await self._settle(match_id, actor)
        self._changed()
        return self.match_view(match_id) or {}

    async def round_complete(
        self, runtime: SceneRuntime, pair: int, round_number: int, scores: dict[int, int | None]
    ) -> None:
        """A pair finished a round: with ``auto_deduct`` the lower score loses a heart.

        A tie costs nobody a heart. Each scene round deducts at most once (unique
        index on scene, round and pair), also after a restart.
        """
        if not self.settings.auto_deduct:
            return
        info = self.pair_info(runtime, pair)
        if info is None or info["winner_id"] is not None:
            return
        a, b = runtime.layout.pairs[pair]
        side = core.loser_of_round(scores.get(a), scores.get(b))
        if side is None:
            log.info("round tied, no heart lost", scene=runtime.slug, pair=pair, round=round_number)
            return
        loser_slot = (a, b)[side]
        player_id = info["slots"][loser_slot]["player_id"]
        try:
            await self.apply(
                info["match_id"], player_id, "lose", source="auto", actor="auto",
                scene=(runtime.slug, round_number, pair),
            )  # fmt: skip
        except IntegrityError:
            log.info("round already counted", scene=runtime.slug, pair=pair, round=round_number)
            return
        except ValueError as exc:
            log.warning("automatic heart not taken", error=str(exc))
            return
        log.info("heart taken automatically", scene=runtime.slug, pair=pair,
                 round=round_number, player=player_id)  # fmt: skip

    async def undo(self, event_id: int, actor: str) -> dict[str, Any]:
        async with self._lock:
            await self._ensure_loaded()
            event = next((e for e in self._events if e.id == event_id), None)
            if event is None or event.undone:
                raise ValueError("no such change (or already undone)")
            async with self.db.session() as session, session.begin():
                await session.execute(
                    update(MatchLifeEvent)
                    .where(MatchLifeEvent.id == event_id)
                    .values(undone_at=datetime.now(UTC))
                )
                await audit.record(
                    session, actor=actor, action="lives_undo", entity="match", entity_id=0,
                    after={"match_id": event.match_id, "event": event.as_dict()},
                )  # fmt: skip
            event.undone = True
            await self._settle(event.match_id, actor)
        self._changed()
        return self.match_view(event.match_id) or {}

    async def undo_last(self, match_id: str, actor: str) -> dict[str, Any]:
        mine = [e for e in self._events if e.match_id == match_id and not e.undone]
        last = mine[-1] if mine else None
        if last is None:
            raise ValueError("nothing to undo")
        return await self.undo(last.id, actor)

    async def set_max(self, match_id: str, max_lives: int | None, actor: str) -> dict[str, Any]:
        if max_lives is not None and not 1 <= max_lives <= core.MAX_LIVES:
            raise ValueError(f"hearts must be 1..{core.MAX_LIVES}")
        async with self._lock:
            await self._ensure_loaded()
            if self._tournament_id is None or self._bracket() is None:
                raise ValueError("fix the bracket first")
            await self._store_series(match_id, max_lives=max_lives)
            self._max[match_id] = max_lives
            await self._settle(match_id, actor)
        self._changed()
        return self.match_view(match_id) or {}

    async def update_settings(self, changes: dict[str, Any], actor: str) -> dict[str, Any]:
        # Defaults may be set before FIX: the tournament row is created unfixed.
        await self.tournament.ensure_tournament()
        async with self._lock:
            await self._ensure_loaded()
            if self._tournament_id is None:  # pragma: no cover - just created
                raise ValueError("no tournament for the active event")
            values = {k: v for k, v in changes.items() if v is not None}
            if "default_lives" in values and not 1 <= values["default_lives"] <= core.MAX_LIVES:
                raise ValueError(f"hearts must be 1..{core.MAX_LIVES}")
            async with self.db.session() as session, session.begin():
                await session.execute(
                    update(Tournament).where(Tournament.id == self._tournament_id).values(**values)
                )
                await audit.record(
                    session, actor=actor, action="update", entity="settings",
                    entity_id="hearts", after=values,
                )  # fmt: skip
            for key, value in values.items():
                setattr(self.settings, key, value)
        self._changed()
        return self.state()

    async def _store_series(self, match_id: str, **values: Any) -> None:
        async with self.db.session() as session, session.begin():
            await session.execute(
                insert(MatchSeries)
                .values(tournament_id=self._tournament_id, match_id=match_id, **values)
                .on_conflict_do_update(
                    index_elements=[MatchSeries.tournament_id, MatchSeries.match_id], set_=values
                )
            )

    async def _settle(self, match_id: str, actor: str) -> None:
        """Bracket winner from the hearts: set at zero, cleared when given back."""
        bracket = self._bracket()
        match = find_match(bracket, match_id) if bracket else None
        if match is None or match.player1 is None or match.player2 is None:
            return
        out = core.loser(self.lives_of(match))
        current = match.winner.user_id if match.winner else None
        if out is not None:
            winner = match.player2 if out == match.player1.user_id else match.player1
            if current != winner.user_id:
                await self.tournament.mutate(
                    "hearts_winner", f"{actor} (Herzen)",
                    lambda s: s.set_winner(match_id, winner.user_id),
                    match_id=match_id, player_id=winner.user_id,
                )  # fmt: skip
            if match_id not in self._decided_by_lives:
                self._decided_by_lives.add(match_id)
                await self._store_series(match_id, decided_by_lives=True)
        elif match_id in self._decided_by_lives:
            if current is not None:
                await self.tournament.mutate(
                    "hearts_clear", f"{actor} (Herzen)",
                    lambda s: s.clear_winner(match_id), match_id=match_id,
                )  # fmt: skip
            self._decided_by_lives.discard(match_id)
            await self._store_series(match_id, decided_by_lives=False)

    # ------------------------------------------------------------ scene pairs

    def binding(self, scene_id: int, pair: int) -> Binding | None:
        return self.bindings.get((scene_id, pair))

    async def bind(self, scene_id: int, pair: int, match_id: str | None, actor: str) -> None:
        """Manual binding (``None`` unbinds; auto binding may take over again)."""
        async with self._lock:
            await self._ensure_loaded()
            if match_id is not None:
                bracket = self._bracket()
                match = find_match(bracket, match_id) if bracket else None
                if match is None or match.kind != MatchKind.REAL or self._tournament_id is None:
                    raise ValueError(f"{match_id} is not a match between two players")
            await self._store_binding(scene_id, pair, match_id, "manual", actor)
        self._changed()

    async def _store_binding(
        self, scene_id: int, pair: int, match_id: str | None, bound_by: str, actor: str
    ) -> None:
        async with self.db.session() as session, session.begin():
            if match_id is None:
                await session.execute(
                    delete(ScenePairMatch).where(
                        ScenePairMatch.scene_id == scene_id, ScenePairMatch.pair == pair
                    )
                )
            else:
                values = {"tournament_id": self._tournament_id, "match_id": match_id,
                          "bound_by": bound_by, "bound_at": datetime.now(UTC)}  # fmt: skip
                await session.execute(
                    insert(ScenePairMatch)
                    .values(scene_id=scene_id, pair=pair, **values)
                    .on_conflict_do_update(
                        index_elements=[ScenePairMatch.scene_id, ScenePairMatch.pair], set_=values
                    )
                )
            if bound_by == "manual":
                await audit.record(
                    session, actor=actor, action="bind", entity="scene", entity_id=scene_id,
                    after={"pair": pair, "match_id": match_id},
                )  # fmt: skip
        if match_id is None:
            self.bindings.pop((scene_id, pair), None)
        else:
            self.bindings[(scene_id, pair)] = Binding(scene_id, pair, match_id, bound_by)
        self._sides.pop((scene_id, pair), None)

    async def auto_bind(self) -> None:
        """Bind pairs whose two stations hold the cards of an open match's players."""
        await self._ensure_loaded()
        if not self.settings.auto_bind or self.scenes is None:
            return
        bracket = self._bracket()
        if bracket is None or self._tournament_id is None:
            return
        open_matches = {
            frozenset((m.player1.user_id, m.player2.user_id)): m
            for m in _all_matches(bracket)
            if m.kind == MatchKind.REAL and m.effective_winner is None
            and m.player1 is not None and m.player2 is not None
        }  # fmt: skip
        changed = False
        for runtime in list(self.scenes.scenes.values()):
            if runtime.qualifying:
                continue  # qualifying scenes play no matches (no hearts)
            for index, (a, b) in enumerate(runtime.layout.pairs):
                id_a, id_b = self._station_player(runtime, a), self._station_player(runtime, b)
                if id_a is None or id_b is None:
                    continue
                match = open_matches.get(frozenset((id_a, id_b)))
                if match is None:
                    continue
                current = self.bindings.get((runtime.id, index))
                if current is not None and current.match_id == match.match_id:
                    continue
                if current is not None and current.bound_by == "manual":
                    old = find_match(bracket, current.match_id)
                    if old is not None and old.effective_winner is None:
                        continue  # a manual binding of an open match always wins
                async with self._lock:
                    await self._store_binding(runtime.id, index, match.match_id, "auto", "auto")
                log.info("scene pair bound", scene=runtime.slug, pair=index, match=match.match_id)
                changed = True
        if changed:
            self._changed()

    def _station_player(self, runtime: SceneRuntime, slot: int) -> int | None:
        cfg = runtime.slots.get(slot)
        if cfg is None or cfg.station_id is None:
            return None
        return self.hub.station(cfg.station_id).player_id

    def _slot_name(self, runtime: SceneRuntime, slot: int) -> str | None:
        cfg = runtime.slots.get(slot)
        if cfg is None:
            return None
        if cfg.name_override:
            return cfg.name_override
        return self.hub.station(cfg.station_id).player_nickname if cfg.station_id else None

    def pair_info(self, runtime: SceneRuntime, index: int) -> dict[str, Any] | None:
        """The bound match of a pair and which slot is which player (for overlays)."""
        binding = self.bindings.get((runtime.id, index))
        bracket = self._bracket()
        if binding is None or bracket is None:
            return None
        match = find_match(bracket, binding.match_id)
        if match is None or match.player1 is None or match.player2 is None:
            return None
        a, b = runtime.layout.pairs[index]
        sides = self._resolve_sides(runtime, index, match, a, b)
        lives = self.lives_of(match)
        winner = match.effective_winner
        return {
            "pair": index,
            "match_id": match.match_id,
            "round_name": _round_name(bracket, match),
            "max_lives": self.max_lives(match.match_id),
            "bound_by": binding.bound_by,
            "winner_id": winner.user_id if winner else None,
            "slots": {
                slot: {"player_id": pid, "lives": lives.get(pid), "result": _result(winner, pid)}
                for slot, pid in sides.items()
            },
        }

    def _resolve_sides(
        self, runtime: SceneRuntime, index: int, match: Match, a: int, b: int
    ) -> dict[int, int]:
        assert match.player1 is not None and match.player2 is not None
        p1, p2 = match.player1.user_id, match.player2.user_id
        names = {normalize_nickname(match.player1.nickname).casefold(): p1,
                 normalize_nickname(match.player2.nickname).casefold(): p2}  # fmt: skip

        def who(slot: int) -> int | None:
            pid = self._station_player(runtime, slot)
            if pid in (p1, p2):
                return pid
            name = self._slot_name(runtime, slot)
            return names.get(normalize_nickname(name).casefold()) if name else None

        other = {p1: p2, p2: p1}
        ida, idb = who(a), who(b)
        if ida is not None:
            sides = {a: ida, b: other[ida]}
        elif idb is not None:
            sides = {b: idb, a: other[idb]}
        else:
            # Nobody known right now (cards removed): keep the last assignment.
            sides = self._sides.get((runtime.id, index)) or {a: p1, b: p2}
            if set(sides.values()) != {p1, p2}:
                sides = {a: p1, b: p2}
        self._sides[(runtime.id, index)] = sides
        return sides

    def slot_target(self, runtime: SceneRuntime, slot: int) -> tuple[str, int]:
        """(match id, player id) behind a scene slot (Stream Deck endpoints)."""
        for index, pair in enumerate(runtime.layout.pairs):
            if slot in pair:
                info = self.pair_info(runtime, index)
                if info is None:
                    raise LookupError("no match is bound to this pair")
                return info["match_id"], info["slots"][slot]["player_id"]
        raise LookupError("this slot has no opponent in the scene's layout")


def _event(row: MatchLifeEvent) -> _Event:
    return _Event(
        id=row.id,
        match_id=row.match_id,
        player_id=row.player_id,
        kind=row.kind,  # type: ignore[arg-type]
        value=row.value,
        source=row.source,
        actor=row.actor,
        created_at=row.created_at or datetime.now(UTC),
        undone=row.undone_at is not None,
    )


def _all_matches(bracket: Bracket) -> list[Match]:
    return [m for rnd in bracket.rounds for m in rnd.matches] + [bracket.third_place_match]


def _round_name(bracket: Bracket, match: Match) -> str:
    if match.match_id == bracket.third_place_match.match_id:
        return THIRD_PLACE_NAME
    for rnd in bracket.rounds:
        if any(m.match_id == match.match_id for m in rnd.matches):
            return rnd.name
    return ""


def _result(winner: Any, player_id: int) -> str | None:
    if winner is None:
        return None
    return "won" if winner.user_id == player_id else "lost"


def _str_keys(values: dict[int, int]) -> dict[str, int]:
    return {str(k): v for k, v in values.items()}
