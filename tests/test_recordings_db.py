"""Recordings: station upload, live-frame fallback, NGF import, replay scenes."""

from __future__ import annotations

import gzip
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.core import playfield
from nestris_ltm.core.ngf import NgfFrame, encode_file, iter_frames
from nestris_ltm.db.models import Game, GameFrame, GameRecording, Station
from nestris_ltm.runtime import Runtime
from nestris_ltm.services.auth import create_api_token
from tests.payload_samples import GAME_END, LIVE, dumps

pytestmark = pytest.mark.db
PREFIX = "retroverse/nestris"
GAME = GAME_END["game_id"]


def game_frames(n: int = 120, gameid: int = 3) -> list[NgfFrame]:
    return [
        NgfFrame(
            gameid=gameid,
            ctime_ms=i * 17,
            score=(i // 10) * 1000,
            lines=i // 10,
            level=18,
            preview="T",
            counts=[i // 5, 0, 0, 0, 0, 0, 0],
            field=[0] * (playfield.CELLS - 10) + [2] * 10,
        )
        for i in range(n)
    ]


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


async def _token(rt: Runtime, scopes: list[str]) -> dict[str, str]:
    async with rt.db.session() as s, s.begin():
        _, plain = await create_api_token(s, "station-1", scopes)
    return {"Authorization": f"Bearer {plain}"}


async def _game_with_frames(rt: Runtime, frames: int = 5) -> int:
    await rt.ingest.handle_message(
        f"{PREFIX}/station-1/event/game_end", dumps(GAME_END).encode(), PREFIX
    )
    await rt.ingest.drain()
    async with rt.db.session() as s, s.begin():
        game_id = await s.scalar(select(Game.id).where(Game.external_id == GAME))
        assert game_id is not None
        s.add_all(
            GameFrame(game_id=game_id, seq=i + 1, t_ms=i * 100, game_state="in_game", score=i * 100,
                      lines=i, level=18, next_piece="I", playfield=bytes(50))
            for i in range(frames)
        )  # fmt: skip
    return game_id


def _client(rt: Runtime) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(rt)), base_url="http://t")


async def test_station_upload(runtime: Runtime) -> None:
    game_id = await _game_with_frames(runtime)
    station = await _token(runtime, ["stations"])
    other = await _token(runtime, ["players:write"])
    body = encode_file(game_frames())
    url = f"/api/stations/station-1/games/{GAME}/ngf"
    async with _client(runtime) as c:
        assert (await c.put(url, content=body)).status_code == 401
        assert (await c.put(url, content=body, headers=other)).status_code == 403
        r = await c.put("/api/stations/station-1/games/nope/ngf", content=body, headers=station)
        assert r.status_code == 404
        r = await c.put(url, content=b"garbage", headers=station)
        assert r.status_code == 400
        bad_sha = {**station, "X-NGF-SHA256": "00" * 32}
        assert (await c.put(url, content=body, headers=bad_sha)).status_code == 400
        r = await c.put(
            "/api/stations/station-9/games/" + GAME + "/ngf", content=body, headers=station
        )
        assert r.status_code == 409

        good = {**station, "X-NGF-SHA256": hashlib.sha256(body).hexdigest()}
        r = await c.put(url, content=body, headers=good)
        assert r.status_code == 201, r.text
        assert r.json()["frames"] == 120 and r.json()["live_frames_pruned"] == 5
        assert (await c.put(url, content=body, headers=good)).status_code == 200  # idempotent

        dl = await c.get(f"/api/games/{game_id}/recording")
        assert dl.headers["x-recording-source"] == "recording"
        assert len(list(iter_frames(dl.content))) == 120
    async with runtime.db.session() as s:
        assert (await s.scalar(select(func.count()).select_from(GameFrame))) == 0
        assert (await s.get(GameRecording, game_id)) is not None

    # Live frames that arrive after the upload are not stored any more.
    await runtime.ingest.handle_message(
        f"{PREFIX}/station-1/live", dumps(LIVE, game_id=GAME).encode(), PREFIX
    )
    assert await runtime.frames.flush() == 0
    runtime.frames._closed.clear()  # e.g. after a restart: the DB check still applies
    await runtime.ingest.handle_message(
        f"{PREFIX}/station-1/live", dumps(LIVE, game_id=GAME).encode(), PREFIX
    )
    assert await runtime.frames.flush() == 0


async def test_download_falls_back_to_live_frames(runtime: Runtime) -> None:
    game_id = await _game_with_frames(runtime, frames=7)
    async with _client(runtime) as c:
        r = await c.get(f"/api/games/{game_id}/recording", params={"download": True})
        assert r.status_code == 200 and r.headers["x-recording-source"] == "live"
        assert "attachment" in r.headers["content-disposition"]
        frames = list(iter_frames(r.content))
        assert [f.score for f in frames] == [i * 100 for i in range(7)]
        assert (await c.get("/api/games/999/recording")).status_code == 404


async def test_import_ngf(runtime: Runtime) -> None:
    admin = {"X-NestrisLTM-Shell-Token": runtime.shell_token}
    data = encode_file(game_frames(gameid=1) + game_frames(gameid=2) + game_frames(n=10, gameid=9))
    async with _client(runtime) as c:
        r = await c.post("/api/games/import", content=data, headers=admin)
        assert r.status_code == 201, r.text
        games = r.json()["games"]
        assert len(games) == 2  # the 10-frame fragment is skipped
        assert games[0]["score"] == 11_000
        assert (
            await c.post("/api/games/import", content=b"nope", headers=admin)
        ).status_code == 400
        assert (await c.post("/api/games/import", content=data)).status_code == 401
        raw = gzip.decompress(data)
        r = await c.post("/api/games/import", content=raw, headers=admin, params={"player_id": 99})
        assert r.status_code == 422
    async with runtime.db.session() as s:
        imported = (await s.scalars(select(Game).where(Game.source == "ngf_import"))).all()
        assert len(imported) == 2 and imported[0].lines == 11 and imported[0].status == "finished"


async def test_replay_scene(runtime: Runtime) -> None:
    game_id = await _game_with_frames(runtime)
    async with runtime.db.session() as s, s.begin():
        s.add(Station(id="st-x"))
    admin = {"X-NestrisLTM-Shell-Token": runtime.shell_token}
    async with _client(runtime) as c:
        await c.post(
            "/api/scenes", json={"slug": "re", "name": "Replay", "layout": "replay"}, headers=admin
        )
        await c.post(
            "/api/scenes", json={"slug": "vs", "name": "VS", "layout": "1v1"}, headers=admin
        )
        r = await c.post(
            "/api/scenes/re/replay", json={"game_id": game_id, "speed": 2}, headers=admin
        )
        assert r.status_code == 200, r.text
        state = (await c.get("/api/scenes/re/state")).json()["state"]
        replay = state["scene"]["settings"]["replay"]
        assert replay["game_id"] == game_id and replay["speed"] == 2 and replay["score"] == 216560
        assert (
            await c.post("/api/scenes/vs/replay", json={"game_id": game_id}, headers=admin)
        ).status_code == 409
        assert (
            await c.post("/api/scenes/re/replay", json={"game_id": 999}, headers=admin)
        ).status_code == 404
        assert (await c.delete("/api/scenes/re/replay", headers=admin)).status_code == 200
        state = (await c.get("/api/scenes/re/state")).json()["state"]
        assert "replay" not in state["scene"]["settings"]
