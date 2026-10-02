"""Highscore standings and the tournament service against a real database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import (
    Event,
    EventHiddenGame,
    EventHiddenStation,
    EventPlayerFlags,
    Game,
    Player,
    Station,
    Tournament,
)
from nestris_ltm.ingest.payloads import LivePayload
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.runtime import Runtime
from nestris_ltm.services import highscore
from nestris_ltm.services.tournament import NoActiveEventError, TournamentService
from tests.payload_samples import LIVE, dumps

pytestmark = pytest.mark.db
NOW = datetime.now(UTC)


async def _seed(db: DatabaseManager, *, with_event: bool = True) -> dict[str, int]:
    """Players A..E, an active event since yesterday and a mix of games."""
    async with db.session() as s, s.begin():
        ids = {}
        for nick in ("Alice", "Bob", "Cara", "Dan", "Eve"):
            p = Player(nickname=nick)
            s.add(p)
            await s.flush()
            ids[nick] = p.id
        s.add_all([Station(id="st-1"), Station(id="st-2")])
        await s.flush()
        event = None
        if with_event:
            event = Event(name="E", slug="e", starts_at=NOW - timedelta(days=1), is_active=True)
            s.add(event)
            await s.flush()
            ids["event"] = event.id

        def game(player: str | None, score: int | None, *, status: str = "finished",
                 station: str = "st-1", ago_h: float = 1, level: int = 18,
                 external: str | None = None) -> Game:  # fmt: skip
            return Game(
                player_id=ids[player] if player else None,
                score=score,
                status=status,
                station_id=station,
                started_at=NOW - timedelta(hours=ago_h),
                end_level=level,
                external_id=external,
            )

        games = {
            "a1": game("Alice", 100_000),
            "a2": game("Alice", 250_000, level=22),
            "b1": game("Bob", 300_000),
            "c_old": game("Cara", 900_000, ago_h=72),  # before the event window
            "c1": game("Cara", 50_000),
            "d_hidden_station": game("Dan", 800_000, station="st-2"),
            "e_hidden_player": game("Eve", 700_000),
            "unassigned": game(None, 10_000),
            "bob_live": game("Bob", None, status="live", external="st-1-live"),
        }
        s.add_all(games.values())
        await s.flush()
        ids.update({k: g.id for k, g in games.items()})
        if event is not None:
            s.add(EventHiddenStation(event_id=event.id, station_id="st-2"))
            s.add(EventPlayerFlags(event_id=event.id, player_id=ids["Eve"], hide_everywhere=True))
            s.add(EventHiddenGame(event_id=event.id, game_id=ids["b1"]))  # Bob's best hidden
    return ids


async def test_standings_respect_event_hiding_and_live(db: DatabaseManager) -> None:
    await _seed(db)
    live = {"st-1-live": highscore.LiveValues(score=275_000, lines=90, level=19)}
    async with db.session() as s:
        event = (await s.scalars(select(Event))).one()
        st = await highscore.compute_standings(s, event, live)

    board = [(e.nickname, e.score, e.is_live) for e in st.leaderboard]
    # Bob's 300k is hidden, his running game (275k) counts live; Cara's 900k is
    # outside the window; Dan's station and Eve are hidden.
    assert board == [("Bob", 275_000, True), ("Alice", 250_000, False), ("Cara", 50_000, False)]
    assert [p.seed for p in st.pool] == [1, 2, 3]
    assert st.stats.total_games == 4 + 1  # a1, a2, c1, unassigned + Bob live
    assert st.stats.total_score == 100_000 + 250_000 + 50_000 + 10_000 + 275_000
    assert st.stats.active_players == 3
    assert st.stats.highest_score == 275_000
    assert st.stats.highest_level == 22


async def test_standings_without_event_count_everything(db: DatabaseManager) -> None:
    await _seed(db, with_event=False)
    async with db.session() as s:
        st = await highscore.compute_standings(s, None, {})
    assert st.leaderboard[0].nickname == "Cara" and st.leaderboard[0].score == 900_000


async def test_tournament_persists_and_reloads(db: DatabaseManager) -> None:
    ids = await _seed(db)
    hub = LiveHub()
    # Bob's best game is hidden; his running game puts him back on the list.
    hub.update_live(
        "st-1", LivePayload.model_validate_json(dumps(LIVE, game_id="st-1-live", score=275_000))
    )
    service = TournamentService(db, hub)
    sub = service.subscribe()

    init = await service.snapshot()
    assert init["bracket"]["is_seeded"] is False
    assert init["view_settings"]["effects_enabled"] is True

    bracket = await service.mutate("size", "test", lambda st: st.set_active_count(4))
    bracket = await service.mutate("fix", "test", lambda st: st.fix())
    assert bracket["is_seeded"] is True and bracket["active_count"] == 4
    final = bracket["rounds"][-1]["matches"][0]
    # 3 players at size 4: seed 1 gets a bye, seeds 2 and 3 play.
    kinds = [m["kind"] for m in bracket["rounds"][0]["matches"]]
    assert kinds == ["BYE", "REAL"]
    semi = bracket["rounds"][0]["matches"][1]
    winner = semi["player1"]["user_id"]
    await service.mutate("winner", "test", lambda st: st.set_winner(semi["match_id"], winner))
    assert final["kind"] in ("PENDING", "REAL")

    messages = []
    while not sub.queue.empty():
        messages.append(sub.queue.get_nowait()["type"])
    assert "bracket_update" in messages

    async with db.session() as s:
        row = (await s.scalars(select(Tournament))).one()
    assert row.is_seeded and row.active_count == 4 and row.winners == {semi["match_id"]: winner}

    # A fresh service (app restart) restores the frozen bracket.
    restored = TournamentService(db, hub)
    snap = await restored.snapshot()
    assert snap["bracket"]["is_seeded"] is True
    assert snap["bracket"]["rounds"][0]["matches"][1]["winner"]["user_id"] == winner

    # Disabling sets the event flag and is reflected in the bracket.
    out = await restored.set_bracket_excluded(ids["Alice"], True, "test")
    assert ids["Alice"] in out["disabled_user_ids"]
    async with db.session() as s:
        flags = await s.get(EventPlayerFlags, (ids["event"], ids["Alice"]))
    assert flags is not None and flags.hide_from_bracket

    with pytest.raises(ValueError):
        await restored.mutate("winner", "test", lambda st: st.set_winner("r9_m9", 1))


async def test_tournament_needs_an_event(db: DatabaseManager) -> None:
    await _seed(db, with_event=False)
    service = TournamentService(db, LiveHub())
    with pytest.raises(NoActiveEventError):
        await service.mutate("fix", "test", lambda st: st.fix())


async def test_view_settings_persist(db: DatabaseManager) -> None:
    service = TournamentService(db, LiveHub())
    await service.snapshot()
    await service.update_view_settings({"font_scale": 1.5, "effects_enabled": False}, "test")
    await service.set_celebration(False, "test")
    fresh = TournamentService(db, LiveHub())
    snap = await fresh.snapshot()
    assert snap["view_settings"]["font_scale"] == 1.5
    assert snap["view_settings"]["effects_enabled"] is False
    assert snap["celebration"] == {"enabled": False}


async def test_live_values_from_hub() -> None:
    hub = LiveHub()
    hub.update_live("st-1", LivePayload.model_validate_json(dumps(LIVE)))
    values = highscore.live_values_from_hub(hub.stations())
    assert values[LIVE["game_id"]].score == 22800


# ---------------------------------------------------------------- HTTP


@pytest.fixture
async def runtime(tmp_path: Path, fresh_db_settings: DatabaseSettings) -> AsyncIterator[Runtime]:
    rt = Runtime(
        load_settings(tmp_path / "none.toml", database=fresh_db_settings, data_dir=tmp_path)
    )
    await rt.db.run_bootstrap()
    try:
        yield rt
    finally:
        await rt.db.dispose()


async def test_tournament_http(runtime: Runtime) -> None:
    await _seed(runtime.db)
    transport = httpx.ASGITransport(app=create_app(runtime), client=("192.168.1.9", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        assert (await client.post("/api/tournament/fix")).status_code == 401
        state = (await client.get("/api/tournament/state")).json()
        assert state["leaderboard"][0]["nickname"] == "Alice"
        assert (await client.get("/view/highscore")).status_code == 200
        assert (await client.get("/kiosk/static/js/flip.js")).status_code == 200
        r = await client.get("/view/tournament-admin", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/#/tournament"

        shell = {"X-NestrisLTM-Shell-Token": runtime.shell_token}
        r = await client.post("/api/tournament/active-count", json={"count": 4}, headers=shell)
        assert r.status_code == 200 and r.json()["active_count"] == 4
        r = await client.post(
            "/api/tournament/winner", json={"match_id": "r1_m1", "user_id": 1}, headers=shell
        )
        assert r.status_code == 400  # not fixed yet
        r = await client.post(
            "/api/tournament/view/settings", json={"box_opacity": 0.5}, headers=shell
        )
        assert r.json()["box_opacity"] == 0.5
        assert (await client.get("/view/tournament-admin", headers=shell)).status_code == 200
