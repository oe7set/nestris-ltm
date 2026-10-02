"""Ingest against a real PostgreSQL: card resolution, upserts, spool worker, frames."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text, update

from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import Game, GameCheat, GameFrame, Player, PlayerCard, Station
from nestris_ltm.ingest import service as ingest_service
from nestris_ltm.ingest.frame_buffer import FrameBuffer
from nestris_ltm.ingest.service import IngestService
from nestris_ltm.ingest.spool import EventSpool
from nestris_ltm.live.broadcast import Subscription
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services import games
from nestris_ltm.services.players import resolve_card
from tests.payload_samples import CHEAT, GAME_END, GAME_START, LIVE, STATUS, dumps

pytestmark = pytest.mark.db
PREFIX = "retroverse/nestris"
GAME_ID = GAME_START["game_id"]


def _service(db: DatabaseManager, tmp_path: Path) -> IngestService:
    return IngestService(db, LiveHub(), FrameBuffer(db), EventSpool(tmp_path / "spool"))


async def _send(
    service: IngestService, kind: str, payload: str, station: str = "station-1"
) -> None:
    await service.handle_message(f"{PREFIX}/{station}/{kind}", payload.encode(), PREFIX)


async def _game(db: DatabaseManager) -> Game:
    async with db.session() as session:
        return (await session.execute(select(Game).where(Game.external_id == GAME_ID))).scalar_one()


# ------------------------------------------------------------------ cards


async def test_resolve_card_learns_uids_and_auto_creates(db: DatabaseManager) -> None:
    async with db.session() as s, s.begin():
        erv = await resolve_card(s, "a1b2", "Erv")  # unknown -> auto-created
        assert await resolve_card(s, "A1B2", "renamed on card") == erv  # uid wins
        assert await resolve_card(s, "C3D4", "ERV") == erv  # second card, name match
        assert await resolve_card(s, "FFFF", None) is None  # blank unknown card
        assert await resolve_card(s, None, None) is None

    async with db.session() as s:
        player = (await s.execute(select(Player))).scalar_one()
        cards = (await s.execute(select(PlayerCard.uid).order_by(PlayerCard.uid))).scalars().all()
    assert player.nickname == "Erv" and player.auto_created
    assert list(cards) == ["A1B2", "C3D4"]


async def test_resolve_card_uses_existing_player_case_insensitive(db: DatabaseManager) -> None:
    async with db.session() as s, s.begin():
        s.add(Player(nickname="MaxPower"))
    async with db.session() as s, s.begin():
        pid = await resolve_card(s, "0001", "maxpower")
    async with db.session() as s:
        assert (await s.execute(select(func.count(Player.id)))).scalar_one() == 1
        player = await s.get(Player, pid)
    assert player is not None and not player.auto_created


# ------------------------------------------------------------------ events


async def test_full_game_flow(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    sub = service.hub.subscribe()

    await _send(service, "status", dumps(STATUS))
    await _send(service, "event/game_start", dumps(GAME_START))
    await _send(service, "event/cheat", dumps(CHEAT))
    await _send(service, "event/game_end", dumps(GAME_END))
    assert len(service.spool.pending()) == 3
    assert await service.drain() == 3
    assert service.spool.pending() == []

    game = await _game(db)
    assert game.status == "finished" and game.score == 216560 and game.clears_tetris == 18
    assert game.valid is True and game.card_name == "Erv" and game.player_id is not None
    assert game.raw_end is not None and game.raw_end["schema"] == 1
    async with db.session() as s:
        assert (await s.execute(select(func.count(GameCheat.id)))).scalar_one() == 1
    assert _drain_kinds(sub) == ["game_start", "cheat", "game_end"]


def _drain_kinds(sub: Subscription) -> list[str]:
    kinds = []
    while not sub.queue.empty():
        message = sub.queue.get_nowait()
        if message["type"] == "game_event":
            kinds.append(message["kind"])
    return kinds


async def test_redelivery_is_idempotent(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    for _ in range(2):
        await _send(service, "event/game_start", dumps(GAME_START))
        await _send(service, "event/cheat", dumps(CHEAT))
        await _send(service, "event/game_end", dumps(GAME_END))
    assert await service.drain() == 6
    async with db.session() as s:
        assert (await s.execute(select(func.count(Game.id)))).scalar_one() == 1
        assert (await s.execute(select(func.count(GameCheat.id)))).scalar_one() == 1


async def test_end_without_start_and_late_start(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    await _send(service, "event/game_end", dumps(GAME_END))
    await _send(service, "event/game_start", dumps(GAME_START))  # arrives late
    await service.drain()
    game = await _game(db)
    assert game.status == "finished" and game.score == 216560


async def test_edited_game_is_not_overwritten(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    await _send(service, "event/game_end", dumps(GAME_END))
    await service.drain()
    async with db.session() as s, s.begin():
        await s.execute(update(Game).values(score=1, is_edited=True))
    await _send(service, "event/game_end", dumps(GAME_END))
    await service.drain()
    assert (await _game(db)).score == 1


async def test_invalid_event_goes_to_failed(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    await _send(service, "event/game_end", dumps(GAME_END, end_reason="exploded"))
    await _send(service, "event/game_start", dumps(GAME_START))
    assert await service.drain() == 1  # the bad event does not block the good one
    assert len(service.spool.failed()) == 1
    assert service.stats.events_failed == 1


async def test_invalid_live_payload_counts_parse_error(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    await _send(service, "live", "{broken")
    assert service.stats.parse_errors == 1


async def test_new_game_closes_unfinished_game_on_same_station(
    db: DatabaseManager, tmp_path: Path
) -> None:
    service = _service(db, tmp_path)
    await _send(service, "event/game_start", dumps(GAME_START))
    later = dumps(GAME_START, game_id="station-1-later", started_at="2026-09-24T09:30:00.000Z")
    await _send(service, "event/game_start", later)
    other_station = dumps(GAME_START, game_id="station-2-x", station="station-2")
    await _send(service, "event/game_start", other_station, station="station-2")
    await service.drain()
    async with db.session() as s:
        rows = dict((await s.execute(select(Game.external_id, Game.status))).all())
    assert rows == {
        GAME_ID: "abandoned",
        "station-1-later": "live",
        "station-2-x": "live",
    }


async def test_abandon_stale_games(db: DatabaseManager) -> None:
    async with db.session() as s, s.begin():
        await games.record_game_start(
            s,
            games.GameStartPayload.model_validate_json(
                dumps(GAME_START, started_at=(datetime.now(UTC) - timedelta(hours=5)).isoformat())
            ),
        )
    async with db.session() as s, s.begin():
        assert await games.abandon_stale_games(s, timedelta(hours=3)) == 1
    assert (await _game(db)).status == "abandoned"


# ------------------------------------------------------------------ frames + stations


async def test_frames_wait_for_game_then_flush(db: DatabaseManager, tmp_path: Path) -> None:
    service = _service(db, tmp_path)
    start = datetime.fromisoformat(GAME_START["started_at"])
    for i in range(5):
        ts = (start + timedelta(milliseconds=100 * i)).isoformat()
        await _send(service, "live", dumps(LIVE, ts=ts, score=1000 * i))

    assert await service.frames.flush() == 0  # game row not there yet
    assert service.frames.pending_count == 5

    await _send(service, "event/game_start", dumps(GAME_START))
    await service.drain()
    assert await service.frames.flush() == 5
    await _send(service, "live", dumps(LIVE, ts=(start + timedelta(seconds=1)).isoformat()))
    assert await service.frames.flush() == 1

    async with db.session() as s:
        rows = (await s.execute(select(GameFrame).order_by(GameFrame.seq))).scalars().all()
    assert [r.seq for r in rows] == [1, 2, 3, 4, 5, 6]
    assert [r.t_ms for r in rows][:3] == [0, 100, 200]
    assert rows[0].playfield is not None and len(rows[0].playfield) == 50


async def test_station_sync(
    db: DatabaseManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingest_service, "STATION_SYNC_INTERVAL_S", 0.01)
    service = _service(db, tmp_path)
    await _send(service, "status", dumps(STATUS))

    task = asyncio.create_task(service.run_station_sync())
    try:
        station = None
        for _ in range(100):
            await asyncio.sleep(0.02)
            async with db.session() as s:
                station = await s.get(Station, "station-1")
            if station is not None:
                break
    finally:
        task.cancel()
    assert station is not None and station.name == "Station 1"
    assert station.last_status is not None and station.last_status["fps"] == 60.0


async def test_schema_has_player_cards(db: DatabaseManager) -> None:
    async with db.session() as s:
        assert (await s.execute(text("SELECT count(*) FROM player_cards"))).scalar_one() == 0
