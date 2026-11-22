"""Attract-mode demo games: recognize, flag, list and purge them.

Stations from 0.4.0 on never send demos. Older stations did, so the host
checks every station game when it ends and again when its recording arrives
(``core/demo.py`` decides), and ``nestris-ltm demo-scan`` checks the games
already stored. A demo gets ``games.is_demo`` and disappears from every list,
ranking and count; it is deleted only by ``nestris-ltm demo-purge``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core import demo as core
from nestris_ltm.core.ngf import NgfError, iter_frames
from nestris_ltm.db.models import Game, GameFrame, GameRecording
from nestris_ltm.services import audit, game_admin

log = logging.getLogger(__name__)

# The crew decided this game is real: scans leave it alone.
MANUAL_NOT_DEMO = "manual_not_demo"
MANUAL_DEMO = "manual"


async def _samples(session: AsyncSession, game_id: int) -> list[core.Sample]:
    """The game's frames: live frames, else the decoded recording."""
    rows = (
        await session.execute(
            select(GameFrame.t_ms, GameFrame.score, GameFrame.lines, GameFrame.level)
            .where(GameFrame.game_id == game_id, GameFrame.game_state == "in_game")
            .order_by(GameFrame.seq)
        )
    ).all()
    if rows:
        return [core.Sample(t, s, ln, lv) for t, s, ln, lv in rows]
    blob = await session.scalar(
        select(GameRecording.ngf_gz).where(GameRecording.game_id == game_id)
    )
    if blob is None:
        return []
    try:
        return [core.Sample(f.ctime_ms, f.score, f.lines, f.level) for f in iter_frames(blob)]
    except (NgfError, OSError, EOFError) as exc:
        log.warning("game %s: recording does not decode (%s)", game_id, exc)
        return []


def _candidate(game: Game) -> bool:
    return (
        game.source == "station"
        and game.demo_reason != MANUAL_NOT_DEMO
        and game.start_level in (None, 0)
        and game.end_reason != "game_over"
    )


async def classify(session: AsyncSession, game: Game) -> core.DemoMatch | None:
    """The demo ``game`` shows, or None for a real game."""
    if not _candidate(game):
        return None
    samples = await _samples(session, game.id)
    if samples:
        return core.classify_frames(
            samples, start_level=game.start_level, end_reason=game.end_reason
        )
    return core.classify_end_values(
        score=game.score,
        lines=game.lines,
        start_level=game.start_level,
        end_level=game.end_level,
        end_reason=game.end_reason,
    )


async def _flag(session: AsyncSession, game: Game, match: core.DemoMatch, actor: str) -> None:
    game.is_demo = True
    game.demo_reason = match.reason[:64]
    await audit.record(
        session, actor=actor, action="demo", entity="game", entity_id=game.id,
        after={"is_demo": True, "demo_reason": game.demo_reason},
    )  # fmt: skip


async def check_game(session: AsyncSession, game_id: int, actor: str = "station") -> bool:
    """Flag the game if it is a demo (after game_end / a recording upload)."""
    game = await session.get(Game, game_id)
    if game is None or game.is_demo or game.status != "finished":
        return bool(game and game.is_demo)
    match = await classify(session, game)
    if match is None:
        return False
    await _flag(session, game, match, actor)
    log.info("game %s is an attract-mode demo (%s)", game_id, match.reason)
    return True


@dataclass(frozen=True)
class ScanHit:
    game: Game
    match: core.DemoMatch


async def scan(session: AsyncSession, *, apply: bool, actor: str = "cli") -> list[ScanHit]:
    """Check every stored station game that may be a demo; flag with ``apply``."""
    games = (
        await session.scalars(
            select(Game)
            .where(
                Game.source == "station",
                Game.is_demo.is_(False),
                Game.status.in_(("finished", "abandoned")),
                or_(Game.start_level.is_(None), Game.start_level == 0),
                or_(Game.end_reason.is_(None), Game.end_reason != "game_over"),
                or_(Game.demo_reason.is_(None), Game.demo_reason != MANUAL_NOT_DEMO),
            )
            .order_by(Game.id)
        )
    ).all()
    hits = []
    for game in games:
        match = await classify(session, game)
        if match is None:
            continue
        hits.append(ScanHit(game, match))
        if apply:
            await _flag(session, game, match, actor)
    return hits


async def flagged(session: AsyncSession) -> list[Game]:
    return list(
        (await session.scalars(select(Game).where(Game.is_demo.is_(True)).order_by(Game.id))).all()
    )


async def purge(session: AsyncSession, *, actor: str = "cli") -> int:
    """Delete every flagged demo (frames and recordings cascade)."""
    games = await flagged(session)
    await game_admin.delete_games(session, games, actor)
    return len(games)


@dataclass(frozen=True)
class Cluster:
    score: int
    lines: int | None
    end_level: int | None
    start_level: int | None
    count: int
    game_ids: list[int]


async def suggest(session: AsyncSession, *, min_count: int = 5) -> list[Cluster]:
    """Groups of identical results: real games never repeat exactly, demos do.

    Finds the demos of ROMs without a fingerprint yet.
    """
    rows = (
        await session.execute(
            select(
                Game.score,
                Game.lines,
                Game.end_level,
                Game.start_level,
                func.count(),
                func.array_agg(Game.id),
            )
            .where(
                Game.source == "station",
                Game.is_demo.is_(False),
                Game.score.is_not(None),
                Game.score > 0,
                or_(Game.demo_reason.is_(None), Game.demo_reason != MANUAL_NOT_DEMO),
            )
            .group_by(Game.score, Game.lines, Game.end_level, Game.start_level)
            .having(func.count() >= min_count)
            .order_by(func.count().desc())
        )
    ).all()
    return [
        Cluster(int(score or 0), lines, end_level, start_level, count, sorted(ids)[:20])
        for score, lines, end_level, start_level, count, ids in rows
    ]


async def set_demo(
    session: AsyncSession, game_ids: Sequence[int], is_demo: bool, actor: str
) -> int:
    """The crew marks games as demo / as real (sticky against later scans)."""
    games = (await session.scalars(select(Game).where(Game.id.in_(list(game_ids))))).all()
    for game in games:
        before = {"is_demo": game.is_demo, "demo_reason": game.demo_reason}
        game.is_demo = is_demo
        game.demo_reason = MANUAL_DEMO if is_demo else MANUAL_NOT_DEMO
        await audit.record(
            session, actor=actor, action="demo", entity="game", entity_id=game.id,
            before=before, after={"is_demo": is_demo, "demo_reason": game.demo_reason},
        )  # fmt: skip
    return len(games)
