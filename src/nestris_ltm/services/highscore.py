"""Highscore list and statistics for the active event.

Counts every *finished* game inside the active event's window plus every
*running* game, whose current score comes from the LiveHub (the database
only stores a game's score when it ends). A running game that beats the
player's best shows up live, marked ``is_live``, exactly like the old
TournamentHigscore list.

Excluded everywhere (list and statistics): soft-deleted players, players
hidden everywhere in the event, games of stations hidden in the event and
games hidden in the event. Games without a player are not listed but still
count towards games and total score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, not_, or_, select, true
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core.bracket import LeaderboardEntry, Player, Stats
from nestris_ltm.db.models import (
    Event,
    EventHiddenGame,
    EventHiddenStation,
    EventPlayerFlags,
    Game,
)
from nestris_ltm.db.models import Player as PlayerRow
from nestris_ltm.services import events
from nestris_ltm.services.players import NICKNAME_MAX


@dataclass(frozen=True, slots=True)
class LiveValues:
    score: int | None
    lines: int | None
    level: int | None


@dataclass
class _Best:
    game_id: int
    player_id: int
    nickname: str
    score: int
    level: int | None
    lines: int | None
    tetris_rate: float | None
    started_at: datetime
    is_live: bool = False


@dataclass
class Standings:
    """Everything the kiosk needs, computed in one pass."""

    leaderboard: list[LeaderboardEntry]
    pool: list[Player]  # bracket seed pool (best first)
    stats: Stats


def visible_games(event: Event | None) -> ColumnElement[bool]:
    """Games that count in ``event`` (window + per-event hiding)."""
    if event is None:
        return true()
    return and_(
        events.in_window(event),
        not_(
            exists().where(EventHiddenGame.event_id == event.id, EventHiddenGame.game_id == Game.id)
        ),
        not_(
            exists().where(
                EventHiddenStation.event_id == event.id,
                EventHiddenStation.station_id == Game.station_id,
            )
        ),
    )


def visible_players(event: Event | None) -> ColumnElement[bool]:
    condition: ColumnElement[bool] = PlayerRow.deleted_at.is_(None)
    if event is not None:
        condition = and_(
            condition,
            not_(
                exists().where(
                    EventPlayerFlags.event_id == event.id,
                    EventPlayerFlags.player_id == PlayerRow.id,
                    EventPlayerFlags.hide_everywhere.is_(True),
                )
            ),
        )
    return condition


async def bracket_excluded(session: AsyncSession, event: Event | None) -> set[int]:
    """Players kept out of the bracket (hidden from the bracket or everywhere)."""
    if event is None:
        return set()
    rows = await session.scalars(
        select(EventPlayerFlags.player_id).where(
            EventPlayerFlags.event_id == event.id,
            (EventPlayerFlags.hide_from_bracket.is_(True))
            | (EventPlayerFlags.hide_everywhere.is_(True)),
        )
    )
    return set(rows)


async def compute_standings(
    session: AsyncSession,
    event: Event | None,
    live: dict[str, LiveValues],
    *,
    display_count: int = 64,
    pool_size: int = 64,
) -> Standings:
    counted = visible_games(event)

    # Best finished game per visible player (DISTINCT ON, ties: earliest first).
    best_rows = (
        await session.execute(
            select(
                Game.id,
                Game.player_id,
                PlayerRow.nickname,
                Game.score,
                Game.end_level,
                Game.lines,
                Game.tetris_rate,
                Game.started_at,
            )
            .join(PlayerRow, PlayerRow.id == Game.player_id)
            .where(
                Game.status == "finished",
                Game.score.is_not(None),
                counted,
                visible_players(event),
            )
            .ext(distinct_on(Game.player_id))
            .order_by(Game.player_id, Game.score.desc(), Game.started_at.asc())
        )
    ).all()
    best: dict[int, _Best] = {
        r.player_id: _Best(
            r.id,
            r.player_id,
            r.nickname,
            r.score,
            r.end_level,
            r.lines,
            r.tetris_rate,
            r.started_at,
        )
        for r in best_rows
    }

    # Running games: values from the live feed.
    live_rows = (
        await session.execute(
            select(
                Game.id,
                Game.external_id,
                Game.player_id,
                PlayerRow.nickname,
                Game.started_at,
                PlayerRow.deleted_at,
            )
            .outerjoin(PlayerRow, PlayerRow.id == Game.player_id)
            .where(Game.status == "live", counted)
        )
    ).all()
    visible_ids = (
        set(
            await session.scalars(
                select(PlayerRow.id).where(
                    PlayerRow.id.in_([r.player_id for r in live_rows if r.player_id]),
                    visible_players(event),
                )
            )
        )
        if live_rows
        else set()
    )
    live_games = 0
    live_total = 0
    live_max_level = 0
    for row in live_rows:
        values = live.get(row.external_id or "")
        if values is None or values.score is None:
            continue
        if row.player_id is not None and row.player_id not in visible_ids:
            continue  # hidden or deleted player: neither listed nor counted
        live_games += 1
        live_total += values.score
        live_max_level = max(live_max_level, values.level or 0)
        if row.player_id is None:
            continue
        current = best.get(row.player_id)
        if current is None or values.score > current.score:
            best[row.player_id] = _Best(
                row.id,
                row.player_id,
                (row.nickname or "")[:NICKNAME_MAX],
                values.score,
                values.level,
                values.lines,
                None,
                row.started_at,
                is_live=True,
            )

    ordered = sorted(best.values(), key=lambda b: (-b.score, b.started_at, b.nickname))
    leaderboard = [
        LeaderboardEntry(
            rank=i,
            user_id=b.player_id,
            nickname=b.nickname,
            score=b.score,
            level=b.level,
            lines=b.lines,
            tetris_rate=b.tetris_rate,
            is_live=b.is_live,
            game_id=b.game_id,
        )
        for i, b in enumerate(ordered[:display_count], start=1)
    ]
    pool = [
        Player(
            user_id=b.player_id,
            nickname=b.nickname,
            highscore=b.score,
            level=b.level,
            lines=b.lines,
            tetris_rate=b.tetris_rate,
            seed=i,
        )
        for i, b in enumerate(ordered[:pool_size], start=1)
    ]

    agg = (
        await session.execute(
            select(
                func.count(Game.id),
                func.coalesce(func.sum(Game.score), 0),
                func.coalesce(func.max(Game.end_level), 0),
            ).where(
                Game.status == "finished",
                Game.score.is_not(None),
                counted,
                or_(
                    Game.player_id.is_(None),
                    Game.player_id.in_(select(PlayerRow.id).where(visible_players(event))),
                ),
            )
        )
    ).one()
    players_count = len(best)
    stats = Stats(
        total_games=int(agg[0] or 0) + live_games,
        active_players=players_count,
        total_score=int(agg[1] or 0) + live_total,
        avg_score=round(sum(b.score for b in best.values()) / players_count, 1)
        if players_count
        else 0.0,
        highest_score=ordered[0].score if ordered else 0,
        highest_level=max(int(agg[2] or 0), live_max_level),
    )
    return Standings(leaderboard=leaderboard, pool=pool, stats=stats)


def live_values_from_hub(stations: list[Any]) -> dict[str, LiveValues]:
    """Current values of running games keyed by the station's game id."""
    out: dict[str, LiveValues] = {}
    for station in stations:
        frame = station.live
        if frame is not None and frame.game_id:
            out[frame.game_id] = LiveValues(frame.score, frame.lines, frame.level)
    return out
