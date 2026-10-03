"""Terminal API: card lookup, registration, player page, self-reported scores."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.db.models import Event, Game, Player, PlayerCard
from nestris_ltm.runtime import Runtime
from nestris_ltm.services.auth import create_api_token

pytestmark = pytest.mark.db
NOW = datetime.now(UTC)
API = "/api/terminal/v1"


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


@pytest.fixture
async def terminal(runtime: Runtime) -> AsyncIterator[httpx.AsyncClient]:
    async with runtime.db.session() as s, s.begin():
        _, token = await create_api_token(s, "terminal-1", ["terminal"])
    transport = httpx.ASGITransport(app=create_app(runtime), client=("192.168.1.30", 1))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", headers={"Authorization": f"Bearer {token}"}
    ) as c:
        yield c


async def test_registration_and_cards(runtime: Runtime, terminal: httpx.AsyncClient) -> None:
    assert (await terminal.get(f"{API}/ping")).json()["ok"] is True
    r = await terminal.get(f"{API}/card/04a1b2c3")
    assert r.json() == {"status": "unknown", "uid": "04A1B2C3", "name": None}
    assert (await terminal.get(f"{API}/card/xyz")).status_code == 422

    assert (await terminal.get(f"{API}/nickname", params={"value": "Erv"})).json()["available"]
    assert not (await terminal.get(f"{API}/nickname", params={"value": "x"})).json()["valid"]

    body = {
        "nickname": "Erv",
        "first_name": "Erwin",
        "email": "erv@example.org",
        "email_consent": True,
        "card_uid": "04a1b2c3",
    }
    r = await terminal.post(f"{API}/players", json=body)
    assert r.status_code == 201, r.text
    player_id = r.json()["player"]["id"]
    assert (
        await terminal.post(f"{API}/players", json={**body, "card_uid": None})
    ).status_code == 409
    other = {"nickname": "Max", "card_uid": "04A1B2C3"}
    assert (await terminal.post(f"{API}/players", json=other)).status_code == 409  # card taken
    bad = {"nickname": "Hä?!"}
    assert (await terminal.post(f"{API}/players", json=bad)).status_code == 422
    bad_mail = {"nickname": "Max", "email": "nope"}
    assert (await terminal.post(f"{API}/players", json=bad_mail)).status_code == 422

    r = await terminal.get(f"{API}/card/04A1B2C3")
    assert r.json()["status"] == "known" and r.json()["player"]["nickname"] == "Erv"
    async with runtime.db.session() as s:
        player = await s.get(Player, player_id)
        assert player is not None and player.email_consent and player.email_consent_at is not None

    # An old card with the name written on it but an unknown uid.
    r = await terminal.get(f"{API}/card/0BADCAFE", params={"name": "erv"})
    assert r.json()["status"] == "name_match" and r.json()["player"]["id"] == player_id
    assert (await terminal.get(f"{API}/card/0BADCAFE", params={"name": "Unbekannt"})).json()[
        "status"
    ] == "unknown"
    r = await terminal.post(f"{API}/card/0badcafe/link", json={"player_id": player_id})
    assert r.status_code == 200
    async with runtime.db.session() as s:
        cards = set(
            await s.scalars(select(PlayerCard.uid).where(PlayerCard.player_id == player_id))
        )
    assert cards == {"04A1B2C3", "0BADCAFE"}


async def test_profile_highscore_and_self_report(
    runtime: Runtime, terminal: httpx.AsyncClient
) -> None:
    async with runtime.db.session() as s, s.begin():
        old = Event(name="2025", slug="e2025", starts_at=NOW - timedelta(days=400),
                    ends_at=NOW - timedelta(days=380))  # fmt: skip
        current = Event(
            name="2026", slug="e2026", starts_at=NOW - timedelta(days=1), is_active=True
        )
        erv, max_ = Player(nickname="Erv"), Player(nickname="Max")
        s.add_all([old, current, erv, max_])
        await s.flush()

        def g(p: Player, score: int, days_ago: float, lines: int = 100, tetris: int = 15) -> Game:
            return Game(player_id=p.id, score=score, status="finished", lines=lines,
                        clears_tetris=tetris, end_level=19,
                        started_at=NOW - timedelta(days=days_ago))  # fmt: skip

        s.add_all(
            [
                g(erv, 500_000, 390),
                g(erv, 300_000, 0.5),
                g(erv, 100_000, 0.4),
                g(max_, 400_000, 0.3),
            ]
        )
        ids = {"erv": erv.id, "max": max_.id}

    profile = (await terminal.get(f"{API}/players/{ids['erv']}")).json()
    assert profile["all_time"]["games"] == 3 and profile["all_time"]["best_score"] == 500_000
    assert profile["all_time"]["tetris_rate"] == pytest.approx(0.6)
    standing = profile["current"]["standing"]
    assert standing["rank"] == 2 and standing["gap_to_next"] == 100_000
    assert standing["next_rank_name"] == "Max"
    assert [e["event"]["name"] for e in profile["events"]] == ["2026", "2025"]
    assert profile["events"][1]["rank"] == 1 and profile["events"][1]["best_score"] == 500_000
    assert len(profile["games"]) == 3

    r = await terminal.post(
        f"{API}/players/{ids['erv']}/games", json={"score": 450_000, "start_level": 18}
    )
    assert r.status_code == 201
    board = (await terminal.get(f"{API}/highscore")).json()
    assert [(e["nickname"], e["score"]) for e in board["entries"]] == [
        ("Erv", 450_000),
        ("Max", 400_000),
    ]
    assert board["entries"][0]["game_id"] == r.json()["game_id"]
    async with runtime.db.session() as s:
        game = await s.get(Game, r.json()["game_id"])
        assert (
            game is not None and game.source == "self_reported" and "Terminal" in (game.notes or "")
        )

    assert (await terminal.get(f"{API}/players/99999")).status_code == 404
    assert (await terminal.get(f"{API}/games/{r.json()['game_id']}/recording")).status_code == 404


async def test_scope_required(runtime: Runtime) -> None:
    async with runtime.db.session() as s, s.begin():
        _, token = await create_api_token(s, "kiosk", ["players:write"])
    transport = httpx.ASGITransport(app=create_app(runtime), client=("192.168.1.30", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get(f"{API}/ping")).status_code == 401
        headers = {"Authorization": f"Bearer {token}"}
        assert (await c.get(f"{API}/ping", headers=headers)).status_code == 403
