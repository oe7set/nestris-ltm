"""Hearts of the 1-vs-1 matches: pure logic, bracket winner, Stream Deck API, overlay."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.core import lives
from nestris_ltm.core.bracket import find_match
from nestris_ltm.core.lives import LifeEvent
from nestris_ltm.db.models import Event, Game, Player, Station
from nestris_ltm.runtime import Runtime

NOW = datetime.now(UTC)


# ---------------------------------------------------------------- pure logic


def test_fold() -> None:
    ev = [
        LifeEvent(1, "lose"),
        LifeEvent(2, "lose"),
        LifeEvent(2, "lose", undone=True),
        LifeEvent(1, "lose"),
        LifeEvent(1, "lose"),  # clamped at 0
        LifeEvent(9, "lose"),  # not in this match (e.g. before a reseed)
    ]
    assert lives.fold(ev, 2, [1, 2]) == {1: 0, 2: 1}
    assert lives.fold([*ev, LifeEvent(1, "set", 2)], 2, [1, 2]) == {1: 2, 2: 1}
    assert lives.fold([LifeEvent(1, "gain")], 3, [1, 2]) == {1: 3, 2: 3}  # clamped at max
    assert lives.fold([LifeEvent(1, "set", 7)], 3, [1]) == {1: 3}


def test_loser_round_and_cycle() -> None:
    assert lives.loser({1: 0, 2: 1}) == 1
    assert lives.loser({1: 1, 2: 1}) is None
    assert lives.loser({1: 0, 2: 0}) is None  # both out: the admin decides
    assert lives.loser_of_round(100, 200) == 0
    assert lives.loser_of_round(300, 200) == 1
    assert lives.loser_of_round(200, 200) is None  # a tie costs nobody a heart
    assert lives.loser_of_round(None, 200) is None
    assert [lives.cycle(v, 2) for v in (2, 1, 0)] == [1, 0, 2]


# ---------------------------------------------------------------- with a database


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


async def _seed(rt: Runtime) -> dict[str, int]:
    """Alice > Bob > Cara > Dan in the active event; stations st-1..st-4."""
    ids: dict[str, int] = {}
    async with rt.db.session() as s, s.begin():
        s.add_all([Station(id=f"st-{i}") for i in range(1, 5)])
        s.add(Event(name="E", slug="e", starts_at=NOW - timedelta(days=1), is_active=True))
        for nick, score in (
            ("Alice", 400_000),
            ("Bob", 300_000),
            ("Cara", 200_000),
            ("Dan", 100_000),
        ):
            p = Player(nickname=nick)
            s.add(p)
            await s.flush()
            ids[nick] = p.id
            s.add(Game(player_id=p.id, score=score, status="finished", station_id="st-1",
                       started_at=NOW - timedelta(hours=1), end_level=19))  # fmt: skip
    return ids


@pytest.mark.db
async def test_hearts_flow(runtime: Runtime) -> None:
    rt = runtime
    ids = await _seed(rt)
    transport = httpx.ASGITransport(app=create_app(rt), client=("192.168.1.50", 5000))
    shell = {"X-NestrisLTM-Shell-Token": rt.shell_token}
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        # Not fixed yet: no hearts.
        r = await client.post("/api/tournament/matches/r1_m1/lives", headers=shell,
                              json={"player_id": ids["Dan"], "action": "lose"})  # fmt: skip
        assert r.status_code == 400

        # The defaults can be set before FIX (Einstellungen): they survive it.
        r = await client.put("/api/tournament/lives/settings", headers=shell,
                             json={"default_lives": 2, "auto_deduct": False})  # fmt: skip
        assert r.status_code == 200, r.text
        assert not r.json()["seeded"] and rt.tournament.tournament_id is not None

        await client.post("/api/tournament/active-count", json={"count": 4}, headers=shell)
        assert (await client.post("/api/tournament/fix", headers=shell)).status_code == 200
        state = (await client.get("/api/tournament/matches", headers=shell)).json()
        assert state["seeded"] and state["settings"]["default_lives"] == 2
        r1 = next(
            m
            for m in state["matches"]
            if {p["id"] for p in m["players"]} == {ids["Alice"], ids["Dan"]}
        )
        mid = r1["match_id"]
        assert [p["lives"] for p in r1["players"]] == [2, 2]

        # Dan loses two rounds: Alice wins the match in the bracket.
        for _ in range(2):
            r = await client.post(f"/api/tournament/matches/{mid}/lives", headers=shell,
                                  json={"player_id": ids["Dan"], "action": "lose"})  # fmt: skip
            assert r.status_code == 200, r.text
        view = r.json()
        assert view["winner_id"] == ids["Alice"] and view["decided_by_lives"]
        match = find_match(rt.tournament.state.bracket(), mid)
        assert (
            match is not None and match.winner is not None and match.winner.user_id == ids["Alice"]
        )

        # Undo the last change: the heart comes back, the winner goes away.
        last = view["events"][-1]["id"]
        assert view["event_id"] == last  # what the UI's undo toast uses
        view = (await client.post(f"/api/tournament/lives/undo/{last}", headers=shell)).json()
        assert view["winner_id"] is None and not view["decided_by_lives"]
        assert {p["nickname"]: p["lives"] for p in view["players"]} == {"Alice": 2, "Dan": 1}

        # A final with three hearts.
        view = (await client.put(f"/api/tournament/matches/{mid}/max-lives", headers=shell,
                                 json={"max_lives": 3})).json()  # fmt: skip
        assert view["max_lives"] == 3
        assert {p["nickname"]: p["lives"] for p in view["players"]} == {"Alice": 3, "Dan": 2}
        bad = await client.post(f"/api/tournament/matches/{mid}/lives", headers=shell,
                                json={"player_id": ids["Bob"], "action": "lose"})  # fmt: skip
        assert bad.status_code == 400  # not in this match

        # A scene pair bound automatically from the cards on the stations.
        r = await client.post("/api/scenes", headers=shell, json={
            "name": "Bühne", "slug": "buehne", "layout": "1v1", "flow": "rounds",
            "slots": [{"slot": 0, "station_id": "st-1"}, {"slot": 1, "station_id": "st-2"}],
        })  # fmt: skip
        assert r.status_code == 201, r.text
        await rt.scenes.load()
        rt.hub.set_player_nickname("st-1", "Dan", ids["Dan"])  # Dan on the left
        rt.hub.set_player_nickname("st-2", "Alice", ids["Alice"])
        await rt.lives.auto_bind()
        scene = rt.scenes.scenes["buehne"]
        assert rt.lives.binding(scene.id, 0) is not None
        st = rt.scenes.compute_state(scene)
        assert st["matches"][0]["match_id"] == mid and st["matches"][0]["bound_by"] == "auto"
        assert st["slots"][0]["lives"] == {"current": 2, "max": 3}  # Dan, by player not order
        assert st["slots"][1]["lives"] == {"current": 3, "max": 3}
        assert st["slots"][0]["player_id"] == ids["Dan"]  # Regie: hearts -/+ per slot

        # A qualifying scene with the same stations is never bound (no hearts there).
        r = await client.post("/api/scenes", headers=shell, json={
            "name": "Quali", "slug": "quali", "layout": "1v1", "flow": "quali",
            "slots": [{"slot": 0, "station_id": "st-1"}, {"slot": 1, "station_id": "st-2"}],
        })  # fmt: skip
        await rt.scenes.load()
        await rt.lives.auto_bind()
        assert rt.lives.binding(rt.scenes.scenes["quali"].id, 0) is None

        # Stream Deck: token scope "control", slot-based URLs.
        r = await client.post(
            "/api/tokens", headers=shell, json={"name": "deck", "scopes": ["control"]}
        )
        deck = {"Authorization": f"Bearer {r.json()['token']}"}
        base = "/api/control/scenes/buehne/slots/0/lives"
        assert (await client.get(base)).status_code == 401
        got = (await client.get(base, headers=deck)).json()
        assert got["player"] == "Dan" and got["lives"] == 2 and got["max"] == 3
        for _ in range(2):  # idempotent
            got = (await client.post(f"{base}/set/1", headers=deck)).json()
        assert got["lives"] == 1
        got = (await client.post(f"{base}/cycle", headers=deck)).json()  # 1 -> 0: Alice wins
        assert got["lives"] == 0 and got["winner_id"] == ids["Alice"]
        st = rt.scenes.compute_state(scene)
        assert st["slots"][0]["match_result"] == "lost" and st["slots"][1]["match_result"] == "won"
        got = (await client.post(f"{base}/undo", headers=deck)).json()
        assert got["lives"] == 1 and got["winner_id"] is None
        got = (await client.post(f"{base}/cycle", headers=deck)).json()
        assert got["lives"] == 0
        got = (await client.post(f"{base}/cycle", headers=deck)).json()  # 0 -> max again
        assert got["lives"] == 3 and got["winner_id"] is None
        # A slot without a bound match / an unknown scene.
        r = await client.post(
            "/api/scenes",
            headers=shell,
            json={"name": "Leer", "slug": "leer", "layout": "1v1", "flow": "rounds"},
        )
        await rt.scenes.load()
        assert (
            await client.post("/api/control/scenes/leer/slots/0/lives/lose", headers=deck)
        ).status_code == 409
        assert (
            await client.post("/api/control/scenes/nope/slots/0/lives/lose", headers=deck)
        ).status_code == 404

        # Manual binding wins over auto; unbinding works.
        other = next(m["match_id"] for m in state["matches"] if m["match_id"] != mid)
        r = await client.put(
            f"/api/scenes/{scene.id}/pairs/0/match", headers=shell, json={"match_id": other}
        )
        assert r.status_code == 200 and r.json()["pair"]["bound_by"] == "manual"
        await rt.lives.auto_bind()
        assert rt.lives.binding(scene.id, 0).match_id == other  # type: ignore[union-attr]

        # Resetting the bracket wipes the hearts and bindings.
        assert (await client.post("/api/tournament/reset", headers=shell)).status_code == 200
        state = (await client.get("/api/tournament/matches", headers=shell)).json()
        r1 = next(m for m in state["matches"] if m["match_id"] == mid)
        assert r1["events"] == [] and r1["max_lives"] == 2 and r1["winner_id"] is None
        assert rt.lives.binding(scene.id, 0) is None


# ---------------------------------------------------------------- rounds per pair, auto deduction


async def _settle_background(rt: Runtime) -> None:
    import asyncio

    while rt.scenes._background:
        await asyncio.gather(*list(rt.scenes._background))


@pytest.mark.db
async def test_pairs_play_their_own_rounds(runtime: Runtime) -> None:
    from tests.test_scenes_db import end, live

    rt = runtime
    await _seed(rt)
    transport = httpx.ASGITransport(app=create_app(rt), client=("192.168.1.50", 5000))
    shell = {"X-NestrisLTM-Shell-Token": rt.shell_token}
    async with httpx.AsyncClient(transport=transport, base_url="http://t", headers=shell) as client:
        r = await client.post("/api/scenes", json={
            "name": "Vier", "slug": "vier", "layout": "2x1v1", "flow": "rounds",
            "slots": [{"slot": i, "station_id": f"st-{i + 1}"} for i in range(4)],
        })  # fmt: skip
        assert r.status_code == 201, r.text
        await rt.scenes.load()
        r = await client.put("/api/settings/scenes", json={"next_round": "auto"})
        assert r.status_code == 200, r.text
        scene = rt.scenes.scenes["vier"]
        for st, game in (("st-1", "a1"), ("st-2", "b1"), ("st-3", "c1"), ("st-4", "d1")):
            live(rt, st, game, 1000)
        end(rt, "st-1", "a1", 50_000)
        end(rt, "st-2", "b1", 60_000)  # pair 0 done, pair 1 still playing
        live(rt, "st-1", "a2", 10)  # auto round: only pair 0 starts over
        state = rt.scenes.compute_state(scene)
        assert [g["round"] for g in state["groups"]] == [2, 1]
        assert state["slots"][2]["status"] == "playing" and state["slots"][0]["status"] == "playing"
        assert state["slots"][1]["status"] == "waiting"
        # Ranks and leaders per pair, not across all four.
        assert {s["slot"]: s["rank"] for s in state["slots"] if s["rank"]} == {0: 1, 2: 1, 3: 2}

        r = await client.post("/api/scenes/vier/rounds?group=1")
        assert r.status_code == 200 and r.json()["rounds"] == {"1": 2}
        assert (await client.post("/api/scenes/vier/rounds?group=5")).status_code == 400
        # Survives a reload from the database.
        await rt.scenes._persist(scene)
        rt.scenes.scenes = {}
        await rt.scenes.load()
        scene = rt.scenes.scenes["vier"]
        assert [scene.group_round(g).number for g in scene.groups()] == [2, 2]
        assert scene.group_round(0).entry(0).game_id == "a2"


@pytest.mark.db
async def test_automatic_deduction(runtime: Runtime) -> None:
    from tests.test_scenes_db import end, live

    rt = runtime
    ids = await _seed(rt)
    transport = httpx.ASGITransport(app=create_app(rt), client=("192.168.1.50", 5000))
    shell = {"X-NestrisLTM-Shell-Token": rt.shell_token}
    async with httpx.AsyncClient(transport=transport, base_url="http://t", headers=shell) as client:
        await client.post("/api/tournament/active-count", json={"count": 4})
        await client.post("/api/tournament/fix")
        await client.post("/api/scenes", json={
            "name": "Bühne", "slug": "buehne", "layout": "1v1", "flow": "rounds",
            "slots": [{"slot": 0, "station_id": "st-1"}, {"slot": 1, "station_id": "st-2"}],
        })  # fmt: skip
        await rt.scenes.load()
        scene = rt.scenes.scenes["buehne"]
        rt.hub.set_player_nickname("st-1", "Alice", ids["Alice"])
        rt.hub.set_player_nickname("st-2", "Dan", ids["Dan"])
        await rt.lives.auto_bind()
        info = rt.lives.pair_info(scene, 0)
        assert info is not None
        mid = info["match_id"]

        def hearts() -> dict[str, int]:
            view = rt.lives.match_view(mid) or {}
            return {p["nickname"]: p["lives"] for p in view["players"]}

        async def play(round_no: int, alice: int, dan: int) -> None:
            live(rt, "st-1", f"a{round_no}", 10)
            live(rt, "st-2", f"d{round_no}", 10)
            end(rt, "st-1", f"a{round_no}", alice)
            end(rt, "st-2", f"d{round_no}", dan)
            await _settle_background(rt)

        # Switched off (default): nothing happens.
        await play(1, 100_000, 50_000)
        assert hearts() == {"Alice": 2, "Dan": 2}

        r = await client.put("/api/tournament/lives/settings", json={"auto_deduct": True})
        assert r.json()["settings"]["auto_deduct"] is True
        await client.post("/api/scenes/buehne/rounds")
        await play(2, 120_000, 80_000)  # Dan lower: loses a heart
        assert hearts() == {"Alice": 2, "Dan": 1}
        event = (rt.lives.match_view(mid) or {})["events"][-1]
        assert event["source"] == "auto" and event["actor"] == "auto"

        # The same round reported again (e.g. after a restart): no second heart.
        rnd = scene.group_round(0)
        await rt.lives.round_complete(scene, 0, rnd.number, {0: 120_000, 1: 80_000})
        assert hearts() == {"Alice": 2, "Dan": 1}

        await client.post("/api/scenes/buehne/rounds")
        await play(3, 90_000, 90_000)  # tie: nobody
        assert hearts() == {"Alice": 2, "Dan": 1}

        await client.post("/api/scenes/buehne/rounds")
        await play(4, 70_000, 200_000)  # Alice lower now
        assert hearts() == {"Alice": 1, "Dan": 1}

        await client.post("/api/scenes/buehne/rounds")
        await play(5, 300_000, 10_000)  # Dan out: Alice wins the match
        assert hearts() == {"Alice": 1, "Dan": 0}
        assert (rt.lives.match_view(mid) or {})["winner_id"] == ids["Alice"]

        # Decided: further rounds take no more hearts.
        await client.post("/api/scenes/buehne/rounds")
        await play(6, 1, 2)
        assert hearts() == {"Alice": 1, "Dan": 0}
