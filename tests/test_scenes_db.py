"""Scene engine: rounds driven by live frames and game events, plus the API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.db.models import AuditLog, SceneRound, SceneRoundEntry, Station
from nestris_ltm.ingest.payloads import LivePayload
from nestris_ltm.runtime import Runtime
from tests.payload_samples import LIVE, dumps

pytestmark = pytest.mark.db


@pytest.fixture
async def runtime(tmp_path: Path, fresh_db_settings: DatabaseSettings) -> AsyncIterator[Runtime]:
    rt = Runtime(
        load_settings(tmp_path / "none.toml", database=fresh_db_settings, data_dir=tmp_path)
    )
    await rt.db.run_bootstrap()
    async with rt.db.session() as s, s.begin():
        s.add_all([Station(id=f"st-{i}") for i in range(1, 5)])
    try:
        yield rt
    finally:
        await rt.db.dispose()


@pytest.fixture
async def client(runtime: Runtime) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(runtime))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-NestrisLTM-Shell-Token": runtime.shell_token},
    ) as c:
        yield c


def live(rt: Runtime, station: str, game: str | None, score: int, *, level: int = 18,
         lines: int = 10, state: str = "in_game", name: str = "P") -> None:  # fmt: skip
    payload = LivePayload.model_validate_json(
        dumps(LIVE, game_id=game, score=score, level=level, lines=lines, game_state=state,
              player={"uid": station.upper().replace("-", ""), "name": name})
    )  # fmt: skip
    rt.hub.update_live(station, payload)


def end(rt: Runtime, station: str, game: str, score: int, level: int = 19) -> None:
    rt.hub.game_event(
        station,
        "game_end",
        {"game_id": game, "score": score, "lines": 50, "level": level, "start_level": 18},
    )


async def make_scene(client: httpx.AsyncClient, **body: Any) -> dict[str, Any]:
    body.setdefault("flow", "rounds")  # the default "phase" is qualifying until FIX
    r = await client.post("/api/scenes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def state_of(rt: Runtime, slug: str) -> dict[str, Any]:
    return rt.scenes.compute_state(rt.scenes.scenes[slug])


async def test_1v1_freeze_and_diff(runtime: Runtime, client: httpx.AsyncClient) -> None:
    await make_scene(
        client, slug="stage", name="Bühne", layout="1v1",
        slots=[{"slot": 0, "station_id": "st-1"}, {"slot": 1, "station_id": "st-2", "name_override": "Gast"}],
    )  # fmt: skip
    sub = runtime.scenes.scenes["stage"].channel.subscribe()

    live(runtime, "st-1", "g1", 100_000, name="Erv")
    live(runtime, "st-2", "g2", 40_000)
    st = state_of(runtime, "stage")
    a, b = st["slots"]
    assert a["status"] == b["status"] == "playing"
    assert a["name"] == "Erv" and b["name"] == "Gast"
    assert a["rank"] == 1 and b["vs_partner"]["points"] == 60_000
    assert b["vs_partner"]["tetrises_needed"] == 3  # 22 800 per tetris at level 18
    assert a["pace"] > a["score"]
    assert sub.queue.get_nowait()["type"] == "frame"

    # Erv tops out at 120k; Gast keeps playing and passes him.
    end(runtime, "st-1", "g1", 120_000)
    live(runtime, "st-1", "g3", 5_000)  # next game on the finished slot: ignored
    live(runtime, "st-2", "g2", 130_000)
    st = state_of(runtime, "stage")
    a, b = st["slots"]
    assert a["status"] == "finished" and a["score"] == 120_000
    assert b["rank"] == 1 and a["vs_partner"]["points"] == 10_000
    assert runtime.scenes.scenes["stage"].frames[0]["game_id"] == "g1"  # g3 not shown

    # Persisted and restored after a restart of the engine.
    await runtime.scenes._persist(runtime.scenes.scenes["stage"])
    runtime.scenes.scenes.clear()
    await runtime.scenes.load()
    restored = runtime.scenes.scenes["stage"].round.entry(0)
    assert restored.finished and restored.score == 120_000 and restored.player_name == "Erv"


async def test_4p_top2_mode_and_rounds(runtime: Runtime, client: httpx.AsyncClient) -> None:
    await make_scene(
        client, slug="quad", name="Vier", layout="4p", mode="top2_advance",
        slots=[{"slot": i, "station_id": f"st-{i + 1}"} for i in range(4)],
    )  # fmt: skip
    for i, score in enumerate((300_000, 100_000, 200_000, 50_000)):
        live(runtime, f"st-{i + 1}", f"g{i}", score)
    end(runtime, "st-1", "g0", 300_000)
    end(runtime, "st-2", "g1", 100_000)
    end(runtime, "st-3", "g2", 200_000)
    st = state_of(runtime, "quad")
    outcomes = {s["slot"]: s["outcome"] for s in st["slots"]}
    assert outcomes == {0: "advanced", 1: "eliminated", 2: None, 3: None}
    d = st["slots"][3]
    assert d["to_advance"]["score"] == 200_000 and d["to_advance"]["points"] == 150_000

    end(runtime, "st-4", "g3", 250_000)
    st = state_of(runtime, "quad")
    assert st["complete"] is True
    assert [s["outcome"] for s in st["slots"]] == [
        "advanced",
        "eliminated",
        "eliminated",
        "advanced",
    ]

    r = await client.post("/api/scenes/quad/rounds")
    assert r.json()["round"] == 2
    st = state_of(runtime, "quad")
    assert all(s["status"] == "waiting" for s in st["slots"])
    async with runtime.db.session() as s:
        rounds_ = (await s.scalars(select(SceneRound).order_by(SceneRound.number))).all()
        assert [r.number for r in rounds_] == [1, 2] and rounds_[0].ended_at is not None


async def test_auto_round_and_reset_slot(runtime: Runtime, client: httpx.AsyncClient) -> None:
    await make_scene(
        client, slug="auto", name="Auto", layout="1v1",
        slots=[{"slot": 0, "station_id": "st-1"}, {"slot": 1, "station_id": "st-2"}],
    )  # fmt: skip
    # One global switch for all scenes in rounds.
    r = await client.put("/api/settings/scenes", json={"next_round": "auto"})
    assert r.json()["next_round"] == "auto"
    assert (await client.put("/api/settings/scenes", json={"next_round": "x"})).status_code == 422
    scene = runtime.scenes.scenes["auto"]
    live(runtime, "st-1", "a1", 10)
    live(runtime, "st-2", "b1", 10)
    end(runtime, "st-1", "a1", 50_000)
    live(runtime, "st-1", "a2", 10)  # b1 still running: ignored, no new round
    assert scene.round.number == 1
    end(runtime, "st-2", "b1", 60_000)
    live(runtime, "st-1", "a2", 10)  # everybody finished: new round starts
    assert scene.round.number == 2 and scene.round.entry(0).game_id == "a2"

    assert (await client.post("/api/scenes/auto/reset-slot", json={"slot": 0})).status_code == 200
    assert scene.round.entry(0).game_id is None


async def test_qualifying_always_shows_the_current_game(
    runtime: Runtime, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_out = await make_scene(
        client, slug="quali", name="Quali", layout="1v1", flow="quali", mode="top2_advance",
        slots=[{"slot": 0, "station_id": "st-1"}, {"slot": 1, "station_id": "st-2"}],
    )  # fmt: skip
    assert scene_out["flow"] == "quali"
    scene = runtime.scenes.scenes["quali"]
    completed: list[int] = []
    monkeypatch.setattr(runtime.scenes, "_round_complete", lambda rt, g: completed.append(g))

    live(runtime, "st-1", "a1", 80_000, name="Erv")
    live(runtime, "st-2", "b1", 10_000)
    end(runtime, "st-1", "a1", 90_000)
    end(runtime, "st-2", "b1", 20_000)
    st = state_of(runtime, "quali")
    assert [s["status"] for s in st["slots"]] == ["finished", "finished"]
    assert st["scene"]["qualifying"] is True
    assert all(s["outcome"] is None for s in st["slots"])  # no rounds: nobody advances
    assert st["matches"] == []  # no hearts either

    # The next game on station 1 replaces the result at once, no new round.
    live(runtime, "st-1", "a2", 1_000)
    st = state_of(runtime, "quali")
    a, b = st["slots"]
    assert a["status"] == "playing" and a["score"] == 1_000
    assert b["status"] == "finished" and a["vs_partner"]["points"] == 19_000  # behind
    assert scene.frames[0]["game_id"] == "a2" and scene.round.number == 1
    assert [t for t, _ in scene.history[0]] == [0]  # graph restarts with the new game

    # Restored after a restart: the latest game of each slot.
    await runtime.scenes._persist(scene)
    runtime.scenes.scenes.clear()
    await runtime.scenes.load()
    restored = runtime.scenes.scenes["quali"]
    assert restored.qualifying and restored.round.entry(0).game_id == "a2"

    # Switching to rounds from the Regie page: a fresh round starts.
    runtime.scenes._phase_known = True
    r = await client.patch(f"/api/scenes/{scene_out['id']}/flow", json={"flow": "rounds"})
    assert r.status_code == 200 and r.json()["flow"] == "rounds"
    switched = runtime.scenes.scenes["quali"]
    assert switched.qualifying is False and switched.round.number == 2


async def test_flow_follows_the_tournament_phase(
    runtime: Runtime, client: httpx.AsyncClient
) -> None:
    await make_scene(
        client, slug="phase", name="Phase", layout="1v1", flow="phase",
        slots=[{"slot": 0, "station_id": "st-1"}, {"slot": 1, "station_id": "st-2"}],
    )  # fmt: skip
    engine = runtime.scenes
    seeded: list[bool | None] = [None]
    engine.seeded_source = lambda: seeded[0]
    scene = engine.scenes["phase"]

    engine._check_phase()  # phase not known yet: nothing changes
    assert scene.qualifying and not engine._phase_known
    seeded[0] = False
    engine._check_phase()
    live(runtime, "st-1", "a1", 70_000)
    end(runtime, "st-1", "a1", 70_000)
    live(runtime, "st-1", "a2", 100)  # qualifying: replaces the result
    assert scene.round.entry(0).game_id == "a2" and scene.round.number == 1

    seeded[0] = True  # FIX: rounds, starting with a fresh round
    engine._check_phase()
    st = state_of(runtime, "phase")
    assert scene.qualifying is False and scene.round.number == 2
    assert st["scene"]["qualifying"] is False and st["scene"]["flow"] == "phase"
    assert all(s["status"] == "waiting" for s in st["slots"])
    live(runtime, "st-1", "a3", 100)
    end(runtime, "st-1", "a3", 5_000)
    live(runtime, "st-1", "a4", 100)  # rounds: one game per slot and round
    assert scene.round.entry(0).game_id == "a3"

    seeded[0] = False  # UNSEED: qualifying again, the round stays
    engine._check_phase()
    assert scene.qualifying and scene.round.number == 2

    # A scene set to "rounds" ignores the phase.
    r = await client.patch(f"/api/scenes/{scene.id}/flow", json={"flow": "rounds"})
    assert r.status_code == 200
    assert engine.scenes["phase"].qualifying is False
    async with runtime.db.session() as s:
        entry = await s.scalar(
            select(AuditLog).where(AuditLog.entity == "scene").order_by(AuditLog.id.desc())
        )
        assert entry is not None and entry.after == {"flow": "rounds", "mode": "none"}


async def test_scene_api_validation_and_state(runtime: Runtime, client: httpx.AsyncClient) -> None:
    layouts = (await client.get("/api/scenes/layouts")).json()
    assert {lay["id"] for lay in layouts} >= {"single", "1v1", "2x1v1", "4p"}
    bad = await client.post("/api/scenes", json={"slug": "Bad Slug", "name": "x", "layout": "1v1"})
    assert bad.status_code == 422
    bad = await client.post("/api/scenes", json={"slug": "x", "name": "x", "layout": "nope"})
    assert bad.status_code == 422
    bad = await client.post(
        "/api/scenes",
        json={
            "slug": "x",
            "name": "x",
            "layout": "single",
            "slots": [{"slot": 0, "station_id": "zzz"}],
        },
    )
    assert bad.status_code == 422
    scene = await make_scene(client, slug="solo", name="Solo", layout="single",
                             slots=[{"slot": 0, "station_id": "st-1"}])  # fmt: skip
    assert (
        await client.post("/api/scenes", json={"slug": "solo", "name": "x", "layout": "single"})
    ).status_code == 409

    r = await client.patch(
        f"/api/scenes/{scene['id']}", json={"name": "Solo 2", "layout": "single_compact"}
    )
    assert r.json()["layout"] == "single_compact"
    public = httpx.ASGITransport(app=create_app(runtime))
    async with httpx.AsyncClient(transport=public, base_url="http://t") as anon:
        state = (await anon.get("/api/scenes/solo/state")).json()
        assert state["state"]["scene"]["layout"] == "single_compact"
        assert (await anon.post("/api/scenes/solo/rounds")).status_code == 401
        assert (await anon.get("/api/scenes/nope/state")).status_code == 404

    async with runtime.db.session() as s:
        assert (await s.scalars(select(SceneRoundEntry))).all() == []
    assert (await client.delete(f"/api/scenes/{scene['id']}")).status_code == 200
    assert "solo" not in runtime.scenes.scenes
