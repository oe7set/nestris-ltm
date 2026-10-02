from __future__ import annotations

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
