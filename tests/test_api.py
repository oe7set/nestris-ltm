"""Admin REST API against a real database (auth, players, games, events, audit)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.runtime import Runtime
from nestris_ltm.services import auth as auth_service
from tests.payload_samples import GAME_END, GAME_START, dumps

pytestmark = pytest.mark.db
PREFIX = "retroverse/nestris"


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


def _client(rt: Runtime, *, remote: bool = False) -> httpx.AsyncClient:
    client_addr = ("192.168.1.50", 5000) if remote else ("127.0.0.1", 5000)
    transport = httpx.ASGITransport(app=create_app(rt), client=client_addr)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def admin(runtime: Runtime) -> AsyncIterator[httpx.AsyncClient]:
    """A client logged in as the first admin (created through setup)."""
    async with _client(runtime) as client:
        r = await client.post("/api/auth/setup", json={"username": "crew", "password": "secret-pw"})
        assert r.status_code == 201, r.text
        yield client


async def _ingest_game(rt: Runtime, **changes: object) -> None:
    await rt.ingest.handle_message(
        f"{PREFIX}/station-1/event/game_start", dumps(GAME_START, **changes).encode(), PREFIX
    )
    await rt.ingest.handle_message(
        f"{PREFIX}/station-1/event/game_end", dumps(GAME_END, **changes).encode(), PREFIX
    )
    await rt.ingest.drain()


# ---------------------------------------------------------------- auth


async def test_setup_login_and_protection(runtime: Runtime) -> None:
    async with _client(runtime, remote=True) as remote:
        me = (await remote.get("/api/auth/me")).json()
        assert me["needs_setup"] is True and me["can_setup"] is False
        # Setup is only allowed on the host.
        r = await remote.post(
            "/api/auth/setup", json={"username": "intruder", "password": "12345678"}
        )
        assert r.status_code == 403
        assert (await remote.get("/api/players")).status_code == 401
        assert (await remote.get("/api/diagnostics")).status_code == 401

    async with _client(runtime) as local:
        r = await local.post("/api/auth/setup", json={"username": "crew", "password": "secret-pw"})
        assert r.status_code == 201
        assert (await local.get("/api/players")).status_code == 200  # cookie set by setup
        r = await local.post("/api/auth/setup", json={"username": "two", "password": "secret-pw"})
        assert r.status_code == 409

    async with _client(runtime, remote=True) as remote:
        r = await remote.post("/api/auth/login", json={"username": "crew", "password": "wrong"})
        assert r.status_code == 401
        r = await remote.post("/api/auth/login", json={"username": "CREW", "password": "secret-pw"})
        assert r.status_code == 200
        assert (await remote.get("/api/auth/me")).json()["authenticated"] is True
        assert (await remote.get("/api/players")).status_code == 200
        await remote.post("/api/auth/logout")
        remote.cookies.clear()
        assert (await remote.get("/api/players")).status_code == 401


async def test_shell_token_and_api_tokens(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    async with _client(runtime, remote=True) as remote:
        headers = {"X-NestrisLTM-Shell-Token": runtime.shell_token}
        assert (await remote.get("/api/players", headers=headers)).status_code == 200
        bad = {"X-NestrisLTM-Shell-Token": "nope"}
        assert (await remote.get("/api/players", headers=bad)).status_code == 401

    r = await admin.post("/api/tokens", json={"name": "kiosk", "scopes": ["players:write"]})
    assert r.status_code == 201
    token = r.json()["token"]
    async with _client(runtime, remote=True) as remote:
        auth = {"Authorization": f"Bearer {token}"}
        assert (await remote.get("/api/players", headers=auth)).status_code == 403  # not admin
    r = await admin.post("/api/tokens", json={"name": "x", "scopes": ["bogus"]})
    assert r.status_code == 422


async def test_stay_signed_in(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    async with _client(runtime, remote=True) as remote:
        creds = {"username": "crew", "password": "secret-pw"}
        r = await remote.post("/api/auth/login", json={**creds, "remember": True})
        assert r.status_code == 200 and r.json()["remember"] is True
        assert f"Max-Age={auth_service.SESSION_TTL_S}" in r.headers["set-cookie"]

        r = await remote.post("/api/auth/login", json={**creds, "remember": False})
        cookie_header = r.headers["set-cookie"]
        assert "Max-Age" not in cookie_header  # a browser-session cookie
        assert (await remote.get("/api/players")).status_code == 200
        # Not renewed: it ends with the browser or after SHORT_SESSION_TTL_S.
        assert "set-cookie" not in (await remote.get("/api/auth/me")).headers


async def test_remembered_login_is_renewed(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    async with runtime.db.session() as s, s.begin():
        secret = await auth_service.session_secret(s)
    now = time.time()
    # A remembered login used 20 days ago: past half its 30 days, renewed.
    old = auth_service.make_session_cookie(secret, 1, "crew", now - 20 * 86400, remember=True)
    fresh = auth_service.make_session_cookie(secret, 1, "crew", now - 86400, remember=True)
    short = auth_service.make_session_cookie(secret, 1, "crew", now - 3600, remember=False)
    async with _client(runtime, remote=True) as remote:
        r = await remote.get("/api/auth/me", headers={"Cookie": f"nltm_session={old}"})
        assert r.json()["authenticated"] is True
        renewed = r.headers["set-cookie"]
        assert f"Max-Age={auth_service.SESSION_TTL_S}" in renewed
        value = renewed.split(";", 1)[0].split("=", 1)[1].strip('"')
        data = auth_service.parse_session_cookie(secret, value)
        assert data is not None and data.remember and data.expires > now + 29 * 86400

        r = await remote.get("/api/auth/me", headers={"Cookie": f"nltm_session={fresh}"})
        assert "set-cookie" not in r.headers  # still young: nothing to do
        r = await remote.get("/api/auth/me", headers={"Cookie": f"nltm_session={short}"})
        assert r.json()["authenticated"] is True and "set-cookie" not in r.headers

    # A non-remembered session runs out after 12 h.
    expired = auth_service.make_session_cookie(secret, 1, "crew", now - 13 * 3600, remember=False)
    assert auth_service.parse_session_cookie(secret, expired) is None


async def test_login_throttle(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    async with _client(runtime, remote=True) as remote:
        codes = [
            (
                await remote.post("/api/auth/login", json={"username": "crew", "password": "x"})
            ).status_code
            for _ in range(7)
        ]
    assert codes[:5] == [401] * 5 and codes[-1] == 429


# ---------------------------------------------------------------- players


async def test_player_crud_merge_cards(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    r = await admin.post("/api/players", json={"nickname": "  Max   Power ", "city": "Wattens"})
    assert r.status_code == 201
    max_id = r.json()["id"]
    assert r.json()["nickname"] == "Max Power"
    assert (await admin.post("/api/players", json={"nickname": "max power"})).status_code == 409

    r = await admin.patch(f"/api/players/{max_id}", json={"first_name": "Max"})
    assert r.json()["first_name"] == "Max"

    # A card typo auto-created "Max Powr" through the ingest; merge it.
    await _ingest_game(runtime, player={"uid": "CAFE01", "name": "Max Powr"})
    players = (await admin.get("/api/players", params={"q": "powr"})).json()["items"]
    assert len(players) == 1 and players[0]["auto_created"]
    typo_id = players[0]["id"]
    r = await admin.post(f"/api/players/{typo_id}/merge", json={"into_id": max_id})
    assert r.json() == {"ok": True, "games": 1, "cards": 1}

    detail = (await admin.get(f"/api/players/{max_id}")).json()
    assert detail["games_total"] == 1 and detail["best_score"] == 216560
    assert [c["uid"] for c in detail["cards"]] == ["CAFE01"]
    assert (await admin.get("/api/players", params={"q": "powr"})).json()["total"] == 0

    assert (
        await admin.post(f"/api/players/{max_id}/cards", json={"uid": "beef02"})
    ).status_code == 201
    assert (await admin.delete(f"/api/players/{max_id}/cards/BEEF02")).status_code == 200
    assert (await admin.delete(f"/api/players/{max_id}/cards/BEEF02")).status_code == 404

    assert (await admin.delete(f"/api/players/{max_id}")).status_code == 200
    assert (await admin.get("/api/players")).json()["total"] == 0
    assert (await admin.post(f"/api/players/{max_id}/restore")).status_code == 200


# ---------------------------------------------------------------- games + events


async def test_games_edit_hide_and_event_window(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    now = datetime.now(UTC)
    r = await admin.post(
        "/api/events",
        json={"name": "Retroverse 2026", "starts_at": (now - timedelta(days=1)).isoformat()},
    )
    assert r.status_code == 201 and r.json()["is_active"] is True  # first event auto-activates
    event_id = r.json()["id"]
    assert r.json()["slug"] == "retroverse-2026"

    # One game inside the window, one long before it.
    await _ingest_game(
        runtime,
        game_id="station-1-new",
        started_at=now.isoformat(),
        ended_at=(now + timedelta(minutes=5)).isoformat(),
    )
    await _ingest_game(runtime, game_id="station-1-old")  # 2026-09-24, before the window

    in_event = (await admin.get("/api/games")).json()
    assert in_event["total"] == 1 and in_event["event"]["id"] == event_id
    assert (await admin.get("/api/games", params={"all_time": True})).json()["total"] == 2
    game_id = in_event["items"][0]["id"]

    r = await admin.patch(f"/api/games/{game_id}", json={"score": 100000, "notes": "OCR misread"})
    assert r.status_code == 200 and r.json()["is_edited"] is True
    # A re-delivered game_end must not undo the correction.
    await _ingest_game(
        runtime,
        game_id="station-1-new",
        started_at=now.isoformat(),
        ended_at=(now + timedelta(minutes=5)).isoformat(),
    )
    assert (await admin.get(f"/api/games/{game_id}")).json()["score"] == 100000

    assert (
        await admin.put(f"/api/games/{game_id}/hidden/{event_id}", json={"reason": "test"})
    ).status_code == 200
    assert (await admin.get("/api/games", params={"hidden": True})).json()["total"] == 1
    assert (await admin.get("/api/games", params={"hidden": False})).json()["total"] == 0
    detail = (await admin.get(f"/api/games/{game_id}")).json()
    assert detail["hidden"] is True and detail["hidden_in"][0]["reason"] == "test"
    await admin.delete(f"/api/games/{game_id}/hidden/{event_id}")

    # Manual entry.
    player = (await admin.post("/api/players", json={"nickname": "Walk-in"})).json()
    r = await admin.post(
        "/api/games", json={"player_id": player["id"], "score": 55555, "start_level": 18}
    )
    assert r.status_code == 201 and r.json()["source"] == "manual"
    assert (
        await admin.post("/api/games", json={"player_id": 99999, "score": 1})
    ).status_code == 422
    assert (await admin.get("/api/games", params={"sort": "score"})).json()["items"][0][
        "score"
    ] == 100000

    # Second event: activate, the first one becomes inactive.
    r = await admin.post(
        "/api/events", json={"name": "Next", "starts_at": (now + timedelta(days=30)).isoformat()}
    )
    assert r.json()["is_active"] is False
    assert (await admin.post(f"/api/events/{r.json()['id']}/activate")).status_code == 200
    listed = {e["name"]: e["is_active"] for e in (await admin.get("/api/events")).json()}
    assert listed == {"Retroverse 2026": False, "Next": True}
    assert (await admin.delete(f"/api/events/{r.json()['id']}")).status_code == 409  # active

    bad = {
        "name": "X",
        "starts_at": now.isoformat(),
        "ends_at": (now - timedelta(hours=1)).isoformat(),
    }
    assert (await admin.post("/api/events", json=bad)).status_code == 422


async def test_audit_log_and_page_registry(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    player = (await admin.post("/api/players", json={"nickname": "Audited"})).json()
    await admin.patch(f"/api/players/{player['id']}", json={"nickname": "Audited2"})
    log = (await admin.get("/api/audit", params={"entity": "player"})).json()["items"]
    assert [e["action"] for e in log] == ["update", "create"]
    assert log[0]["actor"] == "crew"
    assert log[0]["before"] == {"nickname": "Audited"} and log[0]["after"] == {
        "nickname": "Audited2"
    }

    meta = (await admin.get("/api/meta/pages")).json()
    assert meta["base_urls"][0].startswith("http://127.0.0.1:")
    ids = {p["id"] for p in meta["pages"]}
    assert {"dashboard", "players", "games", "events", "pages", "tray-quit"} <= ids


async def test_stations_listing_and_delete(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    await _ingest_game(runtime)
    stations = (await admin.get("/api/stations")).json()
    assert stations[0]["id"] == "station-1" and stations[0]["games"] == 1
    assert (
        await admin.patch("/api/stations/station-1", json={"name": "Bühne links"})
    ).status_code == 200
    assert (await admin.delete("/api/stations/station-1")).status_code == 200
    assert (await admin.get("/api/stations")).json() == []
    games = (await admin.get("/api/games", params={"all_time": True})).json()
    assert games["total"] == 1 and games["items"][0]["station_id"] is None


async def test_station_metrics(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    from tests.payload_samples import STATUS

    perf = {"capture_fps": 50.0, "fps": 49.8, "target_fps": 50.0, "drop_rate": 0.0}
    await runtime.ingest.handle_message(
        f"{PREFIX}/station-1/status", dumps({**STATUS, "perf": perf}).encode(), PREFIX
    )
    r = await admin.get("/api/stations/station-1/metrics")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 1 and points[0]["fps"] == 49.8
    assert (await admin.get("/api/stations/nope/metrics")).json()["points"] == []


async def test_station_config_template_overrides_and_push(
    runtime: Runtime, admin: httpx.AsyncClient
) -> None:
    from nestris_ltm.core import station_config as sc
    from tests.payload_samples import STATUS

    sent: list[tuple[str, dict[str, object]]] = []

    async def sink(station: str, command: dict[str, object]) -> bool:
        sent.append((station, command))
        return True

    runtime.station_config.command_sink = sink
    await _ingest_game(runtime)  # creates the station row
    await runtime.ingest.handle_message(
        f"{PREFIX}/station-1/status", dumps(STATUS).encode(), PREFIX
    )
    report = {"station": "station-1", "rev": None, "state": "none", "values": {}}
    await runtime.ingest.handle_message(
        f"{PREFIX}/station-1/config", dumps(report).encode(), PREFIX
    )

    # Unmanaged: nothing is sent.
    overview = (await admin.get("/api/station-config")).json()
    assert overview["template"] is None
    assert overview["stations"][0]["managed"] is False and sent == []

    bad = await admin.put("/api/station-config/template", json={"values": {"mqtt": {"host": "x"}}})
    assert bad.status_code == 422 and "mqtt.host" in bad.text

    r = await admin.put(
        "/api/station-config/template", json={"values": {"capture": {"fps": 50, "lowres": 0}}}
    )
    assert r.status_code == 200 and r.json()["sent"] == ["station-1"]
    r = await admin.put(
        "/api/stations/station-1/config",
        json={"values": {"capture": {"lowres": 1, "fps": None}}},
    )
    assert r.status_code == 200
    desired = {"capture": {"fps": 50, "lowres": 1}}
    assert sent[-1][1] == {
        "type": "station_config", "op": "set", "rev": sc.revision(desired), "values": desired,
    }  # fmt: skip

    row = (await admin.get("/api/station-config")).json()["stations"][0]
    assert row["overrides"] == {"capture": {"lowres": 1}}
    assert row["desired"] == desired and row["in_sync"] is False

    applied = {**report, "rev": sc.revision(desired), "state": "applied", "values": desired}
    await runtime.ingest.handle_message(
        f"{PREFIX}/station-1/config", dumps(applied).encode(), PREFIX
    )
    assert (await admin.get("/api/station-config")).json()["stations"][0]["in_sync"] is True

    assert (await admin.delete("/api/stations/station-1/config")).status_code == 200
    assert (await admin.put("/api/stations/nope/config", json={"values": {}})).status_code == 404
    audit = (await admin.get("/api/audit", params={"entity": "station_config"})).json()
    assert len(audit["items"]) == 3


# ---------------------------------------------------------------- bulk actions


async def _manual_games(admin: httpx.AsyncClient, player_id: int, scores: list[int]) -> list[int]:
    ids = []
    for score in scores:
        r = await admin.post("/api/games", json={"player_id": player_id, "score": score})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


async def test_bulk_games(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    from sqlalchemy import func, select, text

    from nestris_ltm.db.models import AuditLog, GameFrame, GameRecording, Scene

    now = datetime.now(UTC)
    r = await admin.post(
        "/api/events", json={"name": "Bulk", "starts_at": (now - timedelta(days=1)).isoformat()}
    )
    event_id = r.json()["id"]
    a = (await admin.post("/api/players", json={"nickname": "Alpha"})).json()["id"]
    b = (await admin.post("/api/players", json={"nickname": "Beta"})).json()["id"]
    ids = await _manual_games(admin, a, [100, 200, 300, 400])

    # Hide / unhide in the active event.
    r = await admin.post("/api/games/bulk", json={"ids": ids[:3], "action": "hide"})
    assert r.status_code == 200 and r.json()["affected"] == 3
    listed = (await admin.get("/api/games", params={"hidden": True})).json()
    assert {g["id"] for g in listed["items"]} == set(ids[:3])
    r = await admin.post(
        "/api/games/bulk", json={"ids": ids[:1], "action": "unhide", "event_id": event_id}
    )
    assert r.status_code == 200

    # Assign / unassign.
    r = await admin.post(
        "/api/games/bulk", json={"ids": ids[:2], "action": "assign", "player_id": b}
    )
    assert r.status_code == 200
    assert {(await admin.get(f"/api/games/{i}")).json()["player_id"] for i in ids[:2]} == {b}
    r = await admin.post("/api/games/bulk", json={"ids": ids[2:], "action": "unassign"})
    assert {(await admin.get(f"/api/games/{i}")).json()["player_id"] for i in ids[2:]} == {None}
    bad = await admin.post("/api/games/bulk", json={"ids": ids, "action": "assign"})
    assert bad.status_code == 422  # no player_id
    bad = await admin.post("/api/games/bulk", json={"ids": [1, 1], "action": "delete"})
    assert bad.status_code == 422  # repeated id
    bad = await admin.post(
        "/api/games/bulk", json={"ids": ids[:1], "action": "assign", "player_id": 999_999}
    )
    assert bad.status_code == 422  # unknown player

    # Unknown id: nothing happens at all.
    r = await admin.post("/api/games/bulk", json={"ids": [*ids, 999_999], "action": "delete"})
    assert r.status_code == 404
    assert (await admin.get("/api/games", params={"all_time": True})).json()["total"] == 4

    # Delete: frames, recording and hidden rows go; a replay scene playing one stops.
    async with runtime.db.session() as session, session.begin():
        session.add(GameFrame(game_id=ids[0], seq=1, t_ms=0, game_state="in_game"))
        session.add(GameRecording(game_id=ids[0], ngf_gz=b"x", sha256="0" * 64, size_bytes=1))
        session.add(
            Scene(
                slug="rp", name="Replay", layout="replay", settings={"replay": {"game_id": ids[0]}}
            )
        )
    r = await admin.post("/api/games/bulk", json={"ids": ids[:3], "action": "delete"})
    assert r.status_code == 200 and r.json()["affected"] == 3
    async with runtime.db.session() as session:
        assert await session.scalar(select(func.count()).select_from(GameFrame)) == 0
        assert await session.scalar(select(func.count()).select_from(GameRecording)) == 0
        hidden = await session.scalar(text("SELECT count(*) FROM event_hidden_games"))
        assert hidden == 0
        scene = await session.scalar(select(Scene).where(Scene.slug == "rp"))
        assert scene is not None and "replay" not in scene.settings
        deletes = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity == "game", AuditLog.action == "delete")
        )
        assert deletes == 3
    remaining = (await admin.get("/api/games", params={"all_time": True})).json()
    assert [g["id"] for g in remaining["items"]] == [ids[3]]

    # The single delete route goes through the same code.
    assert (await admin.delete(f"/api/games/{ids[3]}")).status_code == 200
    assert (await admin.get(f"/api/games/{ids[3]}")).status_code == 404


async def test_bulk_hide_needs_an_event(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    a = (await admin.post("/api/players", json={"nickname": "Solo"})).json()["id"]
    ids = await _manual_games(admin, a, [1])
    r = await admin.post("/api/games/bulk", json={"ids": ids, "action": "hide"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "no_active_event"


async def test_bulk_players(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    ids = [
        (await admin.post("/api/players", json={"nickname": n})).json()["id"]
        for n in ("One", "Two", "Three")
    ]
    r = await admin.post("/api/players/bulk", json={"ids": [*ids, 999_999], "action": "delete"})
    assert r.status_code == 200
    body = r.json()
    assert body["affected"] == 3
    assert body["skipped"] == [{"id": 999_999, "reason": "not_found"}]
    listed = (await admin.get("/api/players")).json()
    assert {p["id"] for p in listed["items"]} & set(ids) == set()

    # "Two" is taken again meanwhile: its restore is skipped, the rest goes through.
    await admin.post("/api/players", json={"nickname": "two"})
    r = await admin.post("/api/players/bulk", json={"ids": ids, "action": "restore"})
    body = r.json()
    assert body["affected"] == 2
    assert body["skipped"] == [{"id": ids[1], "reason": "nickname_taken", "nickname": "Two"}]
    r = await admin.post("/api/players/bulk", json={"ids": ids[:1], "action": "restore"})
    assert r.json()["skipped"] == [{"id": ids[0], "reason": "not_deleted"}]


# ---------------------------------------------------------------- sessions


async def test_sessions_end_with_account_password_and_logout_all(
    runtime: Runtime, admin: httpx.AsyncClient
) -> None:
    r = await admin.post("/api/admins", json={"username": "helper", "password": "helper-pw-1"})
    helper_id = r.json()["id"]

    async def login(name: str, password: str) -> httpx.AsyncClient:
        # Own address: the login throttle is per address and process-wide.
        transport = httpx.ASGITransport(app=create_app(runtime), client=("192.168.1.77", 5000))
        client = httpx.AsyncClient(transport=transport, base_url="http://test")
        r = await client.post("/api/auth/login", json={"username": name, "password": password})
        assert r.status_code == 200, r.text
        return client

    # A deleted admin's cookie stops working at once.
    helper = await login("helper", "helper-pw-1")
    assert (await helper.get("/api/players")).status_code == 200
    assert (await admin.delete(f"/api/admins/{helper_id}")).status_code == 200
    assert (await helper.get("/api/players")).status_code == 401
    await helper.aclose()

    # A password change ends the other sessions; the changing browser stays in.
    other = await login("crew", "secret-pw")
    me = (await admin.get("/api/admins")).json()
    crew_id = next(a["id"] for a in me if a["username"] == "crew")
    r = await admin.put(f"/api/admins/{crew_id}/password", json={"password": "new-secret-pw"})
    assert r.status_code == 200
    assert (await admin.get("/api/players")).status_code == 200
    assert (await other.get("/api/players")).status_code == 401
    await other.aclose()

    # Sign out everywhere: same.
    other = await login("crew", "new-secret-pw")
    assert (await admin.post("/api/auth/logout-all")).status_code == 200
    assert (await admin.get("/api/players")).status_code == 200
    assert (await other.get("/api/players")).status_code == 401
    await other.aclose()


# ---------------------------------------------------------------- attention + failed spool


async def test_attention_and_failed_spool(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    def codes(body: dict[str, object]) -> dict[str, int]:
        return {i["code"]: i["count"] for i in body["items"]}  # type: ignore[attr-defined,index]

    # No event yet: that is the first thing to fix.
    assert "no_event" in codes((await admin.get("/api/attention")).json())

    now = datetime.now(UTC)
    await admin.post(
        "/api/events", json={"name": "Att", "starts_at": (now - timedelta(days=1)).isoformat()}
    )
    p = (await admin.post("/api/players", json={"nickname": "Watch"})).json()["id"]
    g1 = (await admin.post("/api/games", json={"player_id": p, "score": 1})).json()["id"]
    await admin.post("/api/games", json={"player_id": p, "score": 2})
    await admin.post("/api/games/bulk", json={"ids": [g1], "action": "unassign"})
    found = codes((await admin.get("/api/attention")).json())
    assert found.get("unassigned_games") == 1
    assert "no_event" not in found
    # Hidden games do not count.
    await admin.post("/api/games/bulk", json={"ids": [g1], "action": "hide"})
    assert "unassigned_games" not in codes((await admin.get("/api/attention")).json())

    # A failed spool event: listed, put back, discarded.
    spool = runtime.spool
    path = spool.append("station-9", "event/game_end", '{"broken": true}')
    spool.fail(path, "unknown payload")
    assert codes((await admin.get("/api/attention")).json()).get("spool_failed") == 1
    listed = (await admin.get("/api/spool/failed")).json()["items"]
    assert [(i["station"], i["reason"]) for i in listed] == [("station-9", "unknown payload")]
    name = listed[0]["name"]
    assert (await admin.post(f"/api/spool/failed/{name}/retry")).status_code == 200
    assert spool.failed() == [] and [x.name for x in spool.pending()] == [name]

    spool.fail(spool.pending()[0], "still unknown")
    assert (await admin.delete(f"/api/spool/failed/{name}")).status_code == 200
    assert spool.failed() == [] and spool.pending() == []
    assert (await admin.delete(f"/api/spool/failed/{name}")).status_code == 404
    assert (await admin.post("/api/spool/failed/..%2Fx/retry")).status_code == 404


async def test_game_by_external_id_and_scene_states(
    runtime: Runtime, admin: httpx.AsyncClient
) -> None:
    await _ingest_game(runtime, game_id="station-1-ext")
    r = await admin.get("/api/games/external/station-1-ext")
    assert r.status_code == 200
    game = r.json()
    assert (await admin.get(f"/api/games/{game['id']}")).json()["external_id"] == "station-1-ext"
    assert (await admin.get("/api/games/external/nope")).status_code == 404

    # No scenes loaded in this runtime: an empty map, not an error.
    states = await admin.get("/api/scenes/states")
    assert states.status_code == 200 and isinstance(states.json(), dict)


# ---------------------------------------------------------------- export, results, schedule


async def test_exports_and_results(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    now = datetime.now(UTC)
    await admin.post(
        "/api/events",
        json={"name": "Export Cup", "starts_at": (now - timedelta(days=1)).isoformat()},
    )
    a = (await admin.post("/api/players", json={"nickname": "Ärger", "email": "a@x.at"})).json()[
        "id"
    ]
    b = (await admin.post("/api/players", json={"nickname": "Bea"})).json()["id"]
    await _manual_games(admin, a, [300_000])
    await _manual_games(admin, b, [500_000, 100])

    res = (await admin.get("/api/results")).json()
    assert res["event"]["name"] == "Export Cup"
    assert [(e["nickname"], e["score"]) for e in res["leaderboard"]] == [
        ("Bea", 500_000),
        ("Ärger", 300_000),
    ]
    assert res["podium"] is None  # not fixed

    r = await admin.get("/api/export/highscore.csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿Rang;Spieler;Score")
    assert "1;Bea;500000" in text and "Ärger" in text

    plain = (await admin.get("/api/export/players.csv")).content.decode("utf-8")
    assert "a@x.at" not in plain and "E-Mail" not in plain
    full = (await admin.get("/api/export/players.csv", params={"contact": True})).content.decode()
    assert "a@x.at" in full

    games = (await admin.get("/api/export/games.csv", params={"q": "Bea"})).content.decode()
    assert games.count("\r\n") == 3  # header + two games


async def test_backup_schedule_settings(runtime: Runtime, admin: httpx.AsyncClient) -> None:
    r = await admin.put(
        "/api/db/schedule", json={"interval_min": 30, "only_during_event": True, "copy_dir": ""}
    )
    assert r.status_code == 200 and r.json()["interval_min"] == 30
    await runtime.backups.load()
    assert runtime.backups.settings.interval_min == 30
    # No active event: nothing is due.
    assert await runtime.backups._due() is False
    bad = await admin.put("/api/db/schedule", json={"interval_min": -5})
    assert bad.status_code == 422
