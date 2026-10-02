"""Simulator -> broker -> MqttIngest -> PostgreSQL, end to end.

Needs NESTRIS_LTM_TEST_MQTT=host:port (a running broker) and a test
database. Uses a unique topic prefix and client ids, so it does not
interfere with a NestrisLTM instance using the same broker.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from nestris_ltm.config import MqttSettings
from nestris_ltm.core import playfield
from nestris_ltm.core.ngf import NgfFrame
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.models import Game, GameFrame, Player
from nestris_ltm.ingest.frame_buffer import FrameBuffer
from nestris_ltm.ingest.mqtt_client import MqttIngest
from nestris_ltm.ingest.service import IngestService
from nestris_ltm.ingest.simulator import StationSimulator
from nestris_ltm.ingest.spool import EventSpool
from nestris_ltm.live.hub import LiveHub
from tests.conftest import TEST_MQTT

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not TEST_MQTT, reason="NESTRIS_LTM_TEST_MQTT not set"),
]


def _synthetic_game(frames: int = 200) -> list[NgfFrame]:
    """A short game: one line every 20 frames, a tetris at the end."""
    game = []
    for i in range(frames):
        lines = i // 20
        if i == frames - 1:
            lines += 4
        game.append(
            NgfFrame(
                gameid=7,
                ctime_ms=i * 17,
                score=lines * 100,
                lines=lines,
                level=18,
                preview="I",
                counts=[i // 10, 0, 0, 0, 0, 0, 0],
                field=[0] * (playfield.CELLS - 10) + [1] * 10,
            )
        )
    return game


async def test_simulated_station_end_to_end(db: DatabaseManager, tmp_path: Path) -> None:
    assert TEST_MQTT is not None
    host, _, port = TEST_MQTT.partition(":")
    prefix = f"nltm-test/{uuid.uuid4().hex[:8]}"
    settings = MqttSettings(
        host=host,
        port=int(port or 1883),
        topic_prefix=prefix,
        client_id=f"nltm-test-host-{uuid.uuid4().hex[:8]}",
    )

    hub = LiveHub()
    frames = FrameBuffer(db)
    ingest = IngestService(db, hub, frames, EventSpool(tmp_path / "spool"))
    mqtt = MqttIngest(settings, ingest)

    tasks = [
        asyncio.create_task(mqtt.run()),
        asyncio.create_task(ingest.run_worker()),
        asyncio.create_task(frames.run(interval_s=0.2)),
    ]
    try:
        for _ in range(100):
            if mqtt.connected:
                break
            await asyncio.sleep(0.05)
        assert mqtt.connected, mqtt.last_error

        sim = StationSimulator(settings, "sim-1", card_name="E2E Player", speed=20)
        assert await sim.run([_synthetic_game()]) == 1

        game = None
        for _ in range(200):
            await asyncio.sleep(0.05)
            async with db.session() as s:
                game = (await s.execute(select(Game))).scalar_one_or_none()
                frame_count = (
                    await s.execute(select(func.count()).select_from(GameFrame))
                ).scalar_one()
            if game is not None and game.status == "finished" and frame_count > 0:
                break
        assert game is not None and game.status == "finished"
        assert game.lines == 13 and game.clears_tetris == 1 and game.station_id == "sim-1"
        assert frame_count > 0

        async with db.session() as s:
            player = (await s.execute(select(Player))).scalar_one()
        assert player.nickname == "E2E Player" and player.auto_created
        assert game.player_id == player.id

        assert hub.station("sim-1").status is not None
        assert ingest.stats.parse_errors == 0
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
