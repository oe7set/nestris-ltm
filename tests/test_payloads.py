from __future__ import annotations

import pytest
from pydantic import ValidationError

from nestris_ltm.ingest.payloads import (
    CheatPayload,
    GameEndPayload,
    GameStartPayload,
    LivePayload,
    PlayerPayload,
    StatusPayload,
)
from nestris_ltm.ingest.service import split_topic
from tests.payload_samples import (
    CHEAT,
    GAME_END,
    GAME_START,
    LIVE,
    OFFLINE,
    PLAYER,
    STATUS,
    dumps,
)


def test_contract_examples_parse() -> None:
    assert StatusPayload.model_validate_json(dumps(STATUS)).game_id == STATUS["game_id"]
    assert StatusPayload.model_validate_json(dumps(OFFLINE)).state == "offline"
    player = PlayerPayload.model_validate_json(dumps(PLAYER))
    assert player.player is not None and player.player.name == "Erv"
    assert LivePayload.model_validate_json(dumps(LIVE)).playfield is not None
    assert GameStartPayload.model_validate_json(dumps(GAME_START)).start_level == 18
    assert CheatPayload.model_validate_json(dumps(CHEAT)).points == 10000
    end = GameEndPayload.model_validate_json(dumps(GAME_END))
    assert end.clears.tetris == 18
    assert end.started_at.tzinfo is not None


def test_unknown_fields_are_ignored() -> None:
    assert LivePayload.model_validate_json(dumps(LIVE, new_field=1)).score == 22800


def test_blank_card_name_is_none() -> None:
    player = PlayerPayload.model_validate_json(dumps(PLAYER, player={"uid": "A1", "name": "  "}))
    assert player.player is not None and player.player.name is None


@pytest.mark.parametrize(
    "bad",
    [
        dumps(LIVE, playfield=["0"] * 20),
        dumps(LIVE, ts="2026-09-24T09:10:10"),  # naive timestamp
        dumps(GAME_END, end_reason="exploded"),
        "not json",
    ],
)
def test_invalid_payloads_rejected(bad: str) -> None:
    with pytest.raises((ValidationError, ValueError)):
        if "end_reason" in bad:
            GameEndPayload.model_validate_json(bad)
        else:
            LivePayload.model_validate_json(bad)


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("retroverse/nestris/station-1/live", ("station-1", "live")),
        ("retroverse/nestris/station-1/event/game_end", ("station-1", "event/game_end")),
        ("retroverse/nestris/station-1", None),
        ("other/station-1/live", None),
    ],
)
def test_split_topic(topic: str, expected: tuple[str, str] | None) -> None:
    assert split_topic(topic, "retroverse/nestris/") == expected
