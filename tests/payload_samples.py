"""Example payloads from nestris-core/docs/STATION.md (the MQTT contract)."""

from __future__ import annotations

import json
from typing import Any

PLAYFIELD = ["0000000000"] * 18 + ["0000000110", "2221103311"]

STATUS = {
    "state": "online", "station": "station-1", "name": "Station 1", "version": "0.2.0",
    "capture": "ok", "capture_detail": "1280x720", "lock": "locked", "game_state": "in_game",
    "rfid": "ok", "game_id": "station-1-1790241008228", "fps": 60.0, "dropped_frames": 0,
    "uptime_s": 3605, "ts": "2026-09-24T09:10:08.228Z",
}  # fmt: skip

OFFLINE = {"state": "offline", "station": "station-1", "ts": None}

PLAYER = {
    "present": True,
    "player": {"uid": "A1B2C3D4", "name": "Erv"},
    "rfid": "ok",
    "ts": "2026-09-24T09:10:00.000Z",
}

LIVE = {
    "game_id": "station-1-1790241008228", "player": {"uid": "A1B2C3D4", "name": "Erv"},
    "game_state": "in_game", "score": 22800, "lines": 4, "level": 18, "next_piece": "I",
    "tetris_rate": 1.0, "burn": 0, "drought": 3, "max_drought": 9, "pps": 0.9876, "pieces": 12,
    "cheated": 0, "confidence": 0.95, "playfield": PLAYFIELD, "ts": "2026-09-24T09:10:10.000Z",
}  # fmt: skip

GAME_START = {
    "game_id": "station-1-1790241008228", "station": "station-1",
    "player": {"uid": "A1B2C3D4", "name": "Erv"}, "started_at": "2026-09-24T09:10:08.228Z",
    "start_level": 18,
}  # fmt: skip

CHEAT = {
    "game_id": "station-1-1790241008228", "station": "station-1",
    "player": {"uid": "A1B2C3D4", "name": "Erv"}, "cheated": 1, "count": 1, "points": 10000,
    "score_before": 45600, "score_after": 55612, "lines_delta": 0,
    "ts": "2026-09-24T09:12:00.000Z",
}  # fmt: skip

GAME_END = {
    "schema": 1, "game_id": "station-1-1790241008228", "station": "station-1",
    "player": {"uid": "A1B2C3D4", "name": "Erv"},
    "started_at": "2026-09-24T09:10:08.228Z", "ended_at": "2026-09-24T09:17:19.428Z",
    "duration_s": 431.2, "active_seconds": 402.9, "end_reason": "game_over",
    "start_level": 18, "end_level": 21, "score": 216560, "lines": 134,
    "clears": {"single": 31, "double": 11, "triple": 3, "tetris": 18},
    "tetris_rate": 0.5373, "burn": 64, "max_drought": 21, "pieces": 527, "pps": 1.31,
    "cheated": 0, "cheat_points": 0, "valid": True,
    "validation": {"issues": [], "metrics": {"frames": 25876, "ingame_frames": 24190}},
}  # fmt: skip


def dumps(payload: dict[str, Any], **changes: Any) -> str:
    return json.dumps({**payload, **changes})
