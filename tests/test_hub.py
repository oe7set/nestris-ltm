from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nestris_ltm.ingest.payloads import LivePayload, PlayerPayload, StatusPayload
from nestris_ltm.live.hub import LiveHub
from tests.payload_samples import LIVE, OFFLINE, PLAYER, STATUS, dumps


def test_state_and_notifications() -> None:
    hub = LiveHub()
    sub = hub.subscribe()

    hub.update_status("station-1", StatusPayload.model_validate_json(dumps(STATUS)))
    hub.update_player("station-1", PlayerPayload.model_validate_json(dumps(PLAYER)))
    hub.update_live("station-1", LivePayload.model_validate_json(dumps(LIVE)))

    snap = hub.snapshot()[0]
    assert snap["online"] is True and snap["stale"] is False
    assert snap["card"] == {"uid": "A1B2C3D4", "name": "Erv"}
    assert snap["live"]["score"] == 22800
    assert [sub.queue.get_nowait()["type"] for _ in range(3)] == ["station", "station", "live"]

    hub.update_status("station-1", StatusPayload.model_validate_json(dumps(OFFLINE)))
    assert hub.snapshot()[0]["online"] is True  # live data just arrived
    hub.station("station-1").live_at = datetime.now(UTC) - timedelta(minutes=1)
    assert hub.snapshot()[0]["online"] is False


def test_slow_subscriber_drops_instead_of_blocking() -> None:
    hub = LiveHub()
    sub = hub.subscribe()
    live = LivePayload.model_validate_json(dumps(LIVE))
    for _ in range(sub.queue.maxsize + 10):
        hub.update_live("s", live)
    assert sub.dropped == 10
    hub.unsubscribe(sub)
    assert hub.subscriber_count == 0


def test_recent_live_data_counts_as_online() -> None:
    hub = LiveHub()
    hub.update_status("station-1", StatusPayload.model_validate_json(dumps(OFFLINE)))
    assert hub.snapshot()[0]["online"] is False
    hub.update_live("station-1", LivePayload.model_validate_json(dumps(LIVE)))
    assert hub.snapshot()[0]["online"] is True


def _live(seq: int | None, ts: datetime, age: float | None = 7.0) -> LivePayload:
    data = {**LIVE, "seq": seq, "frame_age_ms": age, "ts": ts.isoformat()}
    return LivePayload.model_validate_json(dumps(data))


def test_link_stats_count_losses_and_restarts() -> None:
    hub = LiveHub()
    now = datetime.now(UTC)
    for seq in (10, 11, 14, 15):  # 12 and 13 lost on the way
        hub.update_live("station-1", _live(seq, now))
    link = hub.snapshot()[0]["link"]
    assert link["received"] == 4 and link["lost"] == 2
    assert link["loss_rate"] == round(2 / 6, 4)
    assert link["sequenced"] is True and link["frame_age_ms"] == 7.0
    assert link["clock_skew"] is False and link["transport_ms"] is not None
    hub.update_live("station-1", _live(0, now))  # station restarted
    link = hub.snapshot()[0]["link"]
    assert link["restarts"] == 1 and link["lost"] == 2


def test_link_stats_flag_clock_skew_and_old_stations() -> None:
    hub = LiveHub()
    hub.update_live("station-1", _live(None, datetime.now(UTC) - timedelta(minutes=5), None))
    link = hub.snapshot()[0]["link"]
    assert link["sequenced"] is False and link["lost"] == 0
    assert link["clock_skew"] is True and link["transport_ms"] is None
    assert link["frame_age_ms"] is None


def test_status_perf_goes_into_history() -> None:
    hub = LiveHub()
    perf = {"capture_fps": 50.0, "fps": 48.5, "target_fps": 50.0, "drop_rate": 0.03,
            "missing": 1, "engine_ms_p95": 18.2, "cpu_pct": 71.0, "size": "720x576"}  # fmt: skip
    hub.update_status(
        "station-1", StatusPayload.model_validate_json(dumps({**STATUS, "perf": perf}))
    )
    hub.update_status("station-1", StatusPayload.model_validate_json(dumps(OFFLINE)))
    points = hub.history("station-1")
    assert len(points) == 1
    assert points[0]["fps"] == 48.5 and points[0]["drop_rate"] == 0.03
    assert hub.snapshot()[0]["status"]["perf"] is None  # offline status has no perf
    assert hub.history("unknown") == []
