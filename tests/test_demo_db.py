"""Attract-mode demos against a real PostgreSQL: ingest, scan, filters, purge."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from nestris_ltm.core.ngf import iter_frames
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import EventHiddenGame, Game, GameFrame
from nestris_ltm.services import demo, highscore
from tests.payload_samples import GAME_END, GAME_START, dumps
from tests.test_ingest_db import _active_event, _send, _service

pytestmark = pytest.mark.db
DEMO_NGF = Path(__file__).parent / "data" / "demo" / "game-1078.ngf.gz"
DEMO_END = {
    "end_reason": "reset", "start_level": 0, "end_level": 1, "score": 2185, "lines": 13,
    "clears": {"single": 3, "double": 1, "triple": 0, "tetris": 2}, "pieces": 38,
    "duration_s": 77.0,
}  # fmt: skip


async def _store_frames(db: DatabaseManager, external_id: str, cut_ms: int | None = None) -> None:
    async with db.session() as s, s.begin():
        game_id = await s.scalar(select(Game.id).where(Game.external_id == external_id))
        assert game_id is not None
        for seq, f in enumerate(iter_frames(DEMO_NGF.read_bytes())):
            if cut_ms is not None and f.ctime_ms > cut_ms:
                break
            s.add(
                GameFrame(
                    game_id=game_id, seq=seq, t_ms=f.ctime_ms, game_state="in_game",
                    score=f.score, lines=f.lines, level=f.level, next_piece=f.preview,
                )
            )  # fmt: skip


async def _games(db: DatabaseManager) -> list[Game]:
    async with db.session() as s:
        return list((await s.scalars(select(Game).order_by(Game.id))).all())


async def test_demo_from_an_old_station_is_flagged(db: DatabaseManager, tmp_path: Path) -> None:
    await _active_event(db)
    service = _service(db, tmp_path)
    sub = service.hub.subscribe()
    await _send(service, "event/game_start", dumps(GAME_START, start_level=0))
    await service.drain()
    await _store_frames(db, GAME_START["game_id"])
    # Not valid either: still not held for review, it is a demo.
    await _send(service, "event/game_end", dumps(GAME_END, valid=False, **DEMO_END))
    await service.drain()

    (game,) = await _games(db)
    assert game.is_demo and game.demo_reason is not None
    assert game.demo_reason.startswith("frames:nes-ntsc-event:")
    async with db.session() as s:
        assert (await s.scalar(select(func.count()).select_from(EventHiddenGame))) == 0
        counted = await s.scalar(select(func.count(Game.id)).where(highscore.not_hidden()))
        assert counted == 0
    ends = []
    while not sub.queue.empty():
        m = sub.queue.get_nowait()
        if m["type"] == "game_event" and m["kind"] == "game_end":
            ends.append(m["data"])
    assert ends and ends[0]["demo"] is True


async def test_aborted_demo_is_flagged(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    await _send(service, "event/game_start", dumps(GAME_START, start_level=0))
    await service.drain()
    await _store_frames(db, GAME_START["game_id"], cut_ms=10_000)
    end = {**DEMO_END, "score": 45, "lines": 0, "end_level": 0, "duration_s": 10.0}
    await _send(service, "event/game_end", dumps(GAME_END, **end))
    await service.drain()
    (game,) = await _games(db)
    assert game.is_demo


async def test_real_games_are_not_flagged(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    # A normal level-18 game, and a level-0 game ended by reset without frames.
    await _send(service, "event/game_end", dumps(GAME_END))
    level0 = {**DEMO_END, "score": 2190, "lines": 13}
    await _send(service, "event/game_end", dumps(GAME_END, game_id="station-1-2", **level0))
    # The demo's end values, but a game over: the demo never tops out.
    over = {**DEMO_END, "end_reason": "game_over"}
    await _send(service, "event/game_end", dumps(GAME_END, game_id="station-1-3", **over))
    await service.drain()
    assert [g.is_demo for g in await _games(db)] == [False, False, False]


async def test_scan_flag_unflag_purge(db: DatabaseManager, tmp_path: Path) -> None:
    async with db.session() as s, s.begin():
        await demo.scan(s, apply=True)  # nothing yet
    # Store games without the ingest check (as before this feature).
    service = _service(db, tmp_path)
    await _send(service, "event/game_end", dumps(GAME_END))
    for i in range(3):
        await _send(service, "event/game_end", dumps(GAME_END, game_id=f"st-demo-{i}", **DEMO_END))
    await service.drain()
    async with db.session() as s, s.begin():
        for g in (await s.scalars(select(Game))).all():
            g.is_demo, g.demo_reason = False, None

    async with db.session() as s, s.begin():
        dry = await demo.scan(s, apply=False)
        await s.rollback()
    assert len(dry) == 3 and all(h.match.method == "end_values" for h in dry)
    assert not any(g.is_demo for g in await _games(db))

    # Identical results are suggested (before they are flagged).
    async with db.session() as s, s.begin():
        clusters = await demo.suggest(s, min_count=3)
    assert [(c.score, c.count) for c in clusters] == [(2185, 3)]
    async with db.session() as s, s.begin():
        assert len(await demo.scan(s, apply=True)) == 3

    # The crew says one of them is real: it stays real across scans.
    real = next(g for g in await _games(db) if g.is_demo)
    async with db.session() as s, s.begin():
        await demo.set_demo(s, [real.id], False, "admin")
    async with db.session() as s, s.begin():
        assert len(await demo.scan(s, apply=True)) == 0
    async with db.session() as s, s.begin():
        assert await demo.purge(s, actor="test") == 2
    remaining = await _games(db)
    assert len(remaining) == 2 and not any(g.is_demo for g in remaining)
    assert any(g.demo_reason == demo.MANUAL_NOT_DEMO for g in remaining)
