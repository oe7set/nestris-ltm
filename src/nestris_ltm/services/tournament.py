"""Highscore kiosk + tournament bracket: state, persistence and live push.

Replaces TournamentHigscore's poller, BracketManager, view settings and
celebration services. Clients (the kiosk view and the tournament console)
speak the original WebSocket protocol unchanged::

    {"type": "init" | "leaderboard_update" | "stats_update" | "train_update"
             | "bracket_update" | "view_settings" | "view_scroll" | "celebration"
             | "pong", "data": ...}

Data comes from the active event (see ``services/highscore.py``); the bracket
state is stored per event in ``tournaments``; view settings and the
celebration switch in ``settings``. Being "disabled" in the bracket is the
event flag ``hide_from_bracket`` (``hide_everywhere`` implies it), so the
admin UI and the tournament console always agree.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core.bracket import Bracket, BracketState, next_pow2
from nestris_ltm.core.score_train import compute_train
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import (
    Event,
    EventPlayerFlags,
    MatchLifeEvent,
    MatchSeries,
    ScenePairMatch,
    Tournament,
)
from nestris_ltm.live.broadcast import Broadcaster
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services import app_settings, audit, events, highscore

log = structlog.get_logger(__name__)

POLL_INTERVAL_S = 1.0
VIEW_SETTINGS_KEY = "kiosk.view"
CELEBRATION_KEY = "kiosk.celebration"
# Bracket operations after which the hearts of every match start over.
RESET_ACTIONS = frozenset({"fix", "reset", "unseed"})


class NoActiveEventError(RuntimeError):
    pass


class ViewSettings(BaseModel):
    """Presentation of the public view (pushed live to every kiosk)."""

    font_scale: float = Field(default=1.0, ge=0.6, le=2.5)
    autoscroll: bool = False
    effects_enabled: bool = True
    banners_enabled: bool = True
    box_opacity: float = Field(default=1.0, ge=0.25, le=1.0)


class TournamentService(Broadcaster):
    def __init__(self, db: DatabaseManager, hub: LiveHub) -> None:
        super().__init__()
        self.db = db
        self.hub = hub
        self._lock = asyncio.Lock()
        self._event_id: int | None = None
        self._event_name: str | None = None
        self._tournament_id: int | None = None
        self.state = BracketState()
        self.view_settings = ViewSettings()
        self.celebration_enabled = True
        self._last: dict[str, Any] = {}
        self._loaded = False
        # Called after the hearts were wiped (services/match_lives.py).
        self.on_reset: list[Callable[[], None]] = []
        # The active event's bracket was loaded at least once (phase is known).
        self.synced = False

    @property
    def tournament_id(self) -> int | None:
        return self._tournament_id

    # ------------------------------------------------------------ loading

    async def _load_settings(self, session: AsyncSession) -> None:
        view = await app_settings.get(session, VIEW_SETTINGS_KEY)
        if view is not None:
            self.view_settings = ViewSettings.model_validate(view)
        celebration = await app_settings.get(session, CELEBRATION_KEY)
        if celebration is not None:
            self.celebration_enabled = bool(celebration.get("enabled", True))
        self._loaded = True

    async def _sync_event(self, session: AsyncSession) -> Event | None:
        """Track the active event; load its bracket when it changes."""
        event = await events.active_event(session)
        event_id = event.id if event else None
        if event_id != self._event_id:
            self._event_id = event_id
            self._event_name = event.name if event else None
            self._tournament_id = None
            self.state = BracketState()
            if event is not None:
                row = await session.scalar(
                    select(Tournament)
                    .where(Tournament.event_id == event.id)
                    .order_by(Tournament.id)
                    .limit(1)
                )
                if row is not None:
                    self._tournament_id = row.id
                    self.state = BracketState(
                        active_count=row.active_count,
                        is_seeded=row.is_seeded,
                        seeded_at=row.seeded_at.isoformat() if row.seeded_at else None,
                        frozen_seeds=BracketState.seeds_from_json(row.seeds),
                        manual_winners={str(k): int(v) for k, v in row.winners.items()},
                    )
            log.info("tournament scope changed", event_name=self._event_name)
        self.synced = True
        return event

    async def _refresh(self, session: AsyncSession) -> dict[str, Any]:
        """Recompute leaderboard, stats, train and bracket from the database."""
        if not self._loaded:
            await self._load_settings(session)
        event = await self._sync_event(session)
        live = highscore.live_values_from_hub(self.hub.stations())
        standings = await highscore.compute_standings(session, event, live)
        self.state.live_pool = standings.pool
        self.state.disabled = await highscore.bracket_excluded(session, event)
        stats = standings.stats
        return {
            "leaderboard": [e.model_dump(mode="json") for e in standings.leaderboard],
            "stats": stats.model_dump(mode="json"),
            "train": compute_train(stats.total_score).model_dump(mode="json"),
            "bracket": self._bracket_payload(self.state.bracket()),
        }

    def _bracket_payload(self, bracket: Bracket) -> dict[str, Any]:
        data = bracket.model_dump(mode="json")
        data["event"] = self._event_name
        return data

    # ------------------------------------------------------------ live loop

    async def run(self) -> None:
        """Poll the database and push changed payloads (like the old poller)."""
        while True:
            if await self.db.wait_ready(within_s=5.0):
                try:
                    await self.poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("kiosk refresh failed", error=repr(exc))
            await asyncio.sleep(POLL_INTERVAL_S)

    async def poll_once(self) -> None:
        async with self._lock:
            async with self.db.session() as session:
                current = await self._refresh(session)
            self._publish_changes(current)

    def _publish_changes(self, current: dict[str, Any]) -> None:
        for key, message in (
            ("leaderboard", "leaderboard_update"),
            ("stats", "stats_update"),
            ("train", "train_update"),
            ("bracket", "bracket_update"),
        ):
            if current[key] != self._last.get(key):
                self._last[key] = current[key]
                self.publish({"type": message, "data": current[key]})

    async def snapshot(self) -> dict[str, Any]:
        """The ``init`` message payload for a newly connected client."""
        async with self._lock:
            async with self.db.session() as session:
                current = await self._refresh(session)
            # New baseline, so the next poll does not re-send identical data.
            self._publish_changes(current)
        return {
            **current,
            "view_settings": self.view_settings.model_dump(),
            "celebration": {"enabled": self.celebration_enabled},
        }

    # ------------------------------------------------------------ bracket ops

    async def mutate(
        self, action: str, actor: str, fn: Callable[[BracketState], None], **details: Any
    ) -> dict[str, Any]:
        """Apply a bracket operation, persist it, audit it and push the result."""
        async with self._lock:
            async with self.db.session() as session, session.begin():
                current = await self._refresh(session)
                if self._event_id is None:
                    raise NoActiveEventError("create and activate an event first")
                capacity = next_pow2(self.state.active_count)
                fn(self.state)  # may raise ValueError -> 400
                wipe = action in RESET_ACTIONS or (
                    action == "size" and next_pow2(self.state.active_count) != capacity
                )
                if wipe and self._tournament_id is not None:
                    for model in (MatchLifeEvent, MatchSeries, ScenePairMatch):
                        await session.execute(
                            delete(model).where(model.tournament_id == self._tournament_id)
                        )
                await self._persist(session)
                await audit.record(
                    session,
                    actor=actor,
                    action=action,
                    entity="tournament",
                    entity_id=self._tournament_id or 0,
                    after={"event": self._event_name, **details},
                )
            current["bracket"] = self._bracket_payload(self.state.bracket())
            self._publish_changes(current)
            if wipe:
                for callback in self.on_reset:
                    callback()
            bracket: dict[str, Any] = current["bracket"]
            return bracket

    async def _persist(self, session: AsyncSession) -> None:
        values = {
            "active_count": self.state.active_count,
            "is_seeded": self.state.is_seeded,
            "seeds": self.state.seeds_json(),
            "winners": self.state.manual_winners,
            "seeded_at": (
                datetime.fromisoformat(self.state.seeded_at) if self.state.seeded_at else None
            ),
        }
        if self._tournament_id is None:
            row = Tournament(event_id=self._event_id, name=self._event_name or "Turnier", **values)
            session.add(row)
            await session.flush()
            self._tournament_id = row.id
        else:
            row_obj = await session.get(Tournament, self._tournament_id)
            if row_obj is None:  # pragma: no cover - deleted concurrently
                raise NoActiveEventError("tournament row vanished")
            for key, value in values.items():
                setattr(row_obj, key, value)

    async def set_bracket_excluded(
        self, player_id: int, excluded: bool, actor: str
    ) -> dict[str, Any]:
        """Disable/enable a player for the bracket (= event flag hide_from_bracket)."""
        async with self._lock:
            async with self.db.session() as session, session.begin():
                event = await events.active_event(session)
                if event is None:
                    raise NoActiveEventError("create and activate an event first")
                await session.execute(
                    insert(EventPlayerFlags)
                    .values(event_id=event.id, player_id=player_id, hide_from_bracket=excluded)
                    .on_conflict_do_update(
                        index_elements=[EventPlayerFlags.event_id, EventPlayerFlags.player_id],
                        set_={"hide_from_bracket": excluded},
                    )
                )
                await audit.record(
                    session,
                    actor=actor,
                    action="flags",
                    entity="player",
                    entity_id=player_id,
                    after={"event_id": event.id, "hide_from_bracket": excluded},
                )
            async with self.db.session() as session:
                current = await self._refresh(session)
            self._publish_changes(current)
            bracket: dict[str, Any] = current["bracket"]
            return bracket

    # ------------------------------------------------------------ presentation

    async def update_view_settings(self, changes: dict[str, Any], actor: str) -> ViewSettings:
        merged = ViewSettings.model_validate({**self.view_settings.model_dump(), **changes})
        await self._store_setting(VIEW_SETTINGS_KEY, merged.model_dump())
        self.view_settings = merged
        self.publish({"type": "view_settings", "data": merged.model_dump()})
        log.info("kiosk view settings changed", actor=actor, **changes)
        return merged

    def scroll_to(self, position: float) -> None:
        self.publish({"type": "view_scroll", "data": {"position": position}})

    async def set_celebration(self, enabled: bool, actor: str) -> dict[str, bool]:
        await self._store_setting(CELEBRATION_KEY, {"enabled": enabled})
        self.celebration_enabled = enabled
        self.publish({"type": "celebration", "data": {"enabled": enabled}})
        log.info("kiosk celebration changed", actor=actor, enabled=enabled)
        return {"enabled": enabled}

    async def _store_setting(self, key: str, value: dict[str, Any]) -> None:
        async with self.db.session() as session, session.begin():
            await app_settings.put(session, key, value)

    def phase(self) -> dict[str, Any]:
        """Qualifying or tournament, for the admin pages (Regie, Turnier, Dashboard)."""
        st = self.state
        eligible = [p for p in st.live_pool if p.user_id not in st.disabled]
        return {
            "event": self._event_name,
            "has_event": self._event_id is not None,
            "seeded": st.is_seeded,
            "seeded_at": st.seeded_at,
            "active_count": st.active_count,
            "players": len(eligible),
            "known": self.synced,
        }

    def seeded(self) -> bool | None:
        """Tournament phase for the scenes: fixed or not; None until loaded."""
        return self.state.is_seeded if self.synced else None

    async def ensure_tournament(self) -> int:
        """The active event's tournament row (created unfixed if missing)."""
        async with self._lock:
            async with self.db.session() as session, session.begin():
                await self._refresh(session)
                if self._event_id is None:
                    raise NoActiveEventError("create and activate an event first")
                if self._tournament_id is None:
                    await self._persist(session)
            assert self._tournament_id is not None
            return self._tournament_id

    def invalidate(self) -> None:
        """Force a full reload and re-broadcast on the next refresh."""
        self._event_id = -1
        self._last.clear()
