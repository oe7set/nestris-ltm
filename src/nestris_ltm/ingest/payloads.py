"""Pydantic models of the station -> host MQTT contract.

Source of truth: ``nestris-core/crates/nestris-station/src/payload.rs`` and
``nestris-core/docs/STATION.md``. Unknown fields are ignored so a newer
station never breaks the host; missing optional fields default to ``None``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from nestris_ltm.core import playfield


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class CardPlayer(_Payload):
    uid: str = Field(min_length=1, max_length=32)
    # Name written on the card; None for a blank card.
    name: str | None = None

    @field_validator("name")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class StationPerf(_Payload):
    """``perf`` in the status (station 0.3.0+): the last 2-second window."""

    capture_fps: float | None = None
    fps: float | None = None
    target_fps: float | None = None
    drop_rate: float | None = None
    missing: int | None = None
    dropped_total: int | None = None
    missing_total: int | None = None
    engine_ms_p50: float | None = None
    engine_ms_p95: float | None = None
    frame_age_ms_p95: float | None = None
    live_hz: float | None = None
    size: str | None = None
    cpu_pct: float | None = None
    load1: float | None = None


class StatusPayload(_Payload):
    state: Literal["online", "offline"]
    station: str
    name: str | None = None
    version: str | None = None
    capture: str | None = None
    capture_detail: str | None = None
    lock: str | None = None
    game_state: str | None = None
    # ok / offline / outdated (reader firmware with another protocol) / disabled
    rfid: str | None = None
    reader_fw: str | None = None
    reader_serial: str | None = None
    game_id: str | None = None
    fps: float | None = None
    dropped_frames: int | None = None
    perf: StationPerf | None = None
    uptime_s: int | None = None
    ts: AwareDatetime | None = None


class UpdatePayload(_Payload):
    """``<base>/update`` (retained): progress of an update started from here."""

    station: str | None = None
    target: Literal["station", "reader"]
    version: str
    # downloading, verifying, installing, flashing, waiting, done, failed
    state: str = Field(max_length=32)
    detail: str | None = Field(default=None, max_length=500)
    progress: float | None = None
    ts: AwareDatetime | None = None


class ConfigReportPayload(_Payload):
    """``<base>/config`` (retained, station 0.3.0+): the remote configuration."""

    station: str | None = None
    version: str | None = None
    rev: int | None = None
    # none, applied, pending (after the running game), restarting, rejected
    state: str = Field(max_length=16)
    error: str | None = Field(default=None, max_length=2000)
    values: dict[str, Any] = Field(default_factory=dict)
    effective: dict[str, Any] = Field(default_factory=dict)
    locked: list[str] = Field(default_factory=list)
    allowed: list[str] = Field(default_factory=list)
    devices: dict[str, Any] | None = None
    ts: AwareDatetime | None = None


class PlayerPayload(_Payload):
    present: bool
    player: CardPlayer | None = None
    rfid: str | None = None
    ts: AwareDatetime | None = None


class LivePayload(_Payload):
    game_id: str | None = None
    player: CardPlayer | None = None
    game_state: str
    score: int | None = None
    lines: int | None = None
    level: int | None = None
    next_piece: str | None = None
    tetris_rate: float | None = None
    burn: int = 0
    drought: int = 0
    max_drought: int = 0
    pps: float | None = None
    pieces: int = 0
    cheated: int = 0
    confidence: float = 0.0
    playfield: list[str] | None = None
    # Running message number (station 0.3.0+): gaps = lost messages.
    seq: int | None = None
    # Capture read -> publish on the station, ms.
    frame_age_ms: float | None = None
    ts: AwareDatetime

    @field_validator("playfield")
    @classmethod
    def _valid_playfield(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            playfield.cells_from_rows(value)  # raises PlayfieldError (a ValueError)
        return value


class GameStartPayload(_Payload):
    game_id: str = Field(min_length=1, max_length=96)
    station: str
    player: CardPlayer | None = None
    started_at: AwareDatetime
    start_level: int | None = None


class CheatPayload(_Payload):
    game_id: str = Field(min_length=1, max_length=96)
    station: str
    player: CardPlayer | None = None
    cheated: int
    count: int
    points: int
    score_before: int
    score_after: int
    lines_delta: int
    ts: AwareDatetime


class LineClears(_Payload):
    single: int = 0
    double: int = 0
    triple: int = 0
    tetris: int = 0


class Validation(_Payload):
    issues: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class GameEndPayload(_Payload):
    schema_: int = Field(alias="schema")
    game_id: str = Field(min_length=1, max_length=96)
    station: str
    player: CardPlayer | None = None
    started_at: AwareDatetime
    ended_at: AwareDatetime
    duration_s: float
    active_seconds: float | None = None
    end_reason: Literal["game_over", "reset", "signal_lost", "shutdown"]
    start_level: int | None = None
    end_level: int | None = None
    score: int | None = None
    lines: int | None = None
    clears: LineClears = Field(default_factory=LineClears)
    tetris_rate: float | None = None
    burn: int = 0
    max_drought: int = 0
    pieces: int = 0
    pps: float | None = None
    cheated: int = 0
    cheat_points: int = 0
    valid: bool
    validation: Validation = Field(default_factory=Validation)
