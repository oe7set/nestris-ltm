"""Reader greeting at a station: nickname + standing via the reader's ``show``."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import Event, Game, Player, PlayerCard
from nestris_ltm.ingest.frame_buffer import FrameBuffer
from nestris_ltm.ingest.service import IngestService
from nestris_ltm.ingest.spool import EventSpool
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services.reader_display import format_score, greeting_lines

NOW = datetime.now(UTC)
PREFIX = "retroverse/nestris"


def test_greeting_lines() -> None:
    assert format_score(159867) == "159.867"
    assert greeting_lines("Erv", {"rank": 3, "best_score": 159867}) == ["Erv", "Platz 3 · 159.867"]
    assert greeting_lines("Erv", None) == ["Erv", "Viel Glück!"]
    assert greeting_lines("X" * 30, None)[0] == "X" * 21  # the reader shows 21 characters


@pytest.mark.db
async def test_card_at_station_greets_on_the_reader(db: DatabaseManager, tmp_path: Path) -> None:
    async with db.session() as s, s.begin():
        s.add(Event(name="2026", slug="e2026", starts_at=NOW - timedelta(days=1), is_active=True))
        erv, max_ = Player(nickname="Erv"), Player(nickname="Max")
        s.add_all([erv, max_])
        await s.flush()
        s.add(PlayerCard(uid="04A1B2C3", player_id=erv.id, card_name="Erv"))
        for p, score in ((erv, 159_867), (max_, 300_000)):
            s.add(
                Game(
                    player_id=p.id,
                    score=score,
                    status="finished",
                    started_at=NOW - timedelta(hours=1),
                )
            )

    sent: list[tuple[str, dict[str, Any]]] = []

    async def sink(station: str, command: dict[str, Any]) -> bool:
        sent.append((station, command))
        return True

    service = IngestService(db, LiveHub(), FrameBuffer(db), EventSpool(tmp_path / "spool"))
    service.command_sink = sink

    async def place(uid: str, name: str | None) -> None:
        payload = {"present": True, "player": {"uid": uid, "name": name}, "rfid": "ok"}
        await service.handle_message(f"{PREFIX}/station-2/player", json.dumps(payload), PREFIX)
        for _ in range(100):
            if not service._background:
                break
            await asyncio.sleep(0.01)

    await place("04a1b2c3", "renamed")  # the uid identifies the player, not the name
    assert sent == [
        ("station-2", {"type": "show", "uid": "04a1b2c3", "lines": ["Erv", "Platz 2 · 159.867"]})
    ]
    await place("0B0B0B0B", None)  # unknown blank card: the reader's own screen stays
    assert len(sent) == 1
    await place("0C0C0C0C", "Max")  # old card with only the name
    assert sent[-1][1]["lines"] == ["Max", "Platz 1 · 300.000"]
