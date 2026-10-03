"""Player profiles for the terminal: statistics over all games and per event."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import Event, Game, GameFrame, GameRecording, Player
from nestris_ltm.services import events, highscore

COUNTED_STATUSES = ("finished",)
RECENT_GAMES = 100


def _stats_row(row: Any) -> dict[str, Any]:
    games = int(row.games or 0)
    lines = int(row.lines or 0)
    tetris_lines = int(row.tetris or 0) * 4
    return {
        "games": games,
        "best_score": row.best,
        "avg_score": round(float(row.avg), 0) if row.avg is not None else None,
        "total_score": int(row.total or 0),
        "total_lines": lines,
        "best_level": row.best_level,
        "tetris_rate": round(tetris_lines / lines, 4) if lines else None,
        "first_game": row.first.isoformat() if row.first else None,
        "last_game": row.last.isoformat() if row.last else None,
    }


def _aggregates() -> list[Any]:
    return [
        func.count(Game.id).label("games"),
        func.max(Game.score).label("best"),
        func.avg(Game.score).label("avg"),
        func.sum(Game.score).label("total"),
        func.sum(Game.lines).label("lines"),
        func.sum(Game.clears_tetris).label("tetris"),
        func.max(Game.end_level).label("best_level"),
        func.min(Game.started_at).label("first"),
        func.max(Game.started_at).label("last"),
    ]


async def standing_in(
    session: AsyncSession, event: Event | None, player_id: int, live: dict[str, Any]
) -> dict[str, Any] | None:
    """Rank, best score and the gap to the next place in ``event``'s highscore."""
    standings = await highscore.compute_standings(
        session, event, live, display_count=100_000, pool_size=0
    )
    board = standings.leaderboard
    for i, entry in enumerate(board):
        if entry.user_id == player_id:
            ahead = board[i - 1] if i > 0 else None
            return {
                "rank": entry.rank,
                "players": len(board),
                "best_score": entry.score,
                "best_game_id": entry.game_id,
                "next_rank_score": ahead.score if ahead else None,
                "gap_to_next": (ahead.score - entry.score) if ahead else None,
                "next_rank_name": ahead.nickname if ahead else None,
            }
    return None


async def profile(session: AsyncSession, player: Player, live: dict[str, Any]) -> dict[str, Any]:
    pid = player.id
    counted = Game.player_id == pid, Game.status.in_(COUNTED_STATUSES), Game.score.is_not(None)

    all_time = (await session.execute(select(*_aggregates()).where(*counted))).one()

    active = await events.active_event(session)
    event_rows = (await session.scalars(select(Event).order_by(Event.starts_at.desc()))).all()
    history = []
    for event in event_rows:
        row = (
            await session.execute(select(*_aggregates()).where(*counted, events.in_window(event)))
        ).one()
        if not row.games:
            continue
        standing = await standing_in(session, event, pid, live if event.is_active else {})
        history.append(
            {
                "event": {
                    "id": event.id,
                    "name": event.name,
                    "starts_at": event.starts_at.isoformat(),
                },
                "active": event.is_active,
                **_stats_row(row),
                "rank": standing["rank"] if standing else None,
                "players": standing["players"] if standing else None,
            }
        )

    current = None
    if active is not None:
        standing = await standing_in(session, active, pid, live)
        row = (
            await session.execute(select(*_aggregates()).where(*counted, events.in_window(active)))
        ).one()
        current = {
            "event": {"id": active.id, "name": active.name},
            **_stats_row(row),
            "standing": standing,
        }

    games = (
        await session.execute(
            select(
                Game,
                or_(
                    select(GameRecording.game_id).where(GameRecording.game_id == Game.id).exists(),
                    select(GameFrame.game_id).where(GameFrame.game_id == Game.id).exists(),
                ).label("has_replay"),
            )
            .where(Game.player_id == pid, Game.status != "abandoned")
            .order_by(Game.started_at.desc())
            .limit(RECENT_GAMES)
        )
    ).all()
    return {
        "player": {"id": player.id, "nickname": player.nickname},
        "all_time": _stats_row(all_time),
        "current": current,
        "events": history,
        "games": [
            {
                "id": g.id,
                "started_at": g.started_at.isoformat(),
                "status": g.status,
                "source": g.source,
                "station_id": g.station_id,
                "score": g.score,
                "lines": g.lines,
                "start_level": g.start_level,
                "end_level": g.end_level,
                "tetris_rate": g.tetris_rate,
                "replay": bool(has_replay),
            }
            for g, has_replay in games
        ],
    }
