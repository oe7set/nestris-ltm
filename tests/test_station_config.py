from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import pytest

from nestris_ltm.core import station_config as sc
from nestris_ltm.ingest.payloads import ConfigReportPayload, StatusPayload
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services import station_config as service_mod
from nestris_ltm.services.station_config import StationConfigError, StationConfigService
from tests.payload_samples import STATUS, dumps

# ---------------------------------------------------------------- core


def test_allowlist_mirrors_the_station() -> None:
    assert sc.is_allowed("capture.scale_width")
    assert sc.is_allowed("engine.calibration.acquire_downscale_width")
    assert sc.is_allowed("station.name")
    for key in ("station.id", "mqtt.host", "host.token", "update.enabled", "capture", "capture."):
        assert not sc.is_allowed(key), key


def test_check_names_every_denied_key() -> None:
    assert sc.check({"capture": {"lowres": 1}}) == {"capture": {"lowres": 1}}
    with pytest.raises(sc.ConfigError, match=r"host\.url, mqtt\.host"):
        sc.check({"mqtt": {"host": "x", "live_max_hz": 30}, "host": {"url": "y"}})
    with pytest.raises(sc.ConfigError):
        sc.check([1, 2])


def test_merge_prune_and_revision() -> None:
    template = {"capture": {"fps": 50, "scale_width": 720}, "session": {"min_game_frames": 120}}
    overrides = {"capture": {"scale_width": 480}}
    merged = sc.merge(template, overrides)
    assert merged == {
        "capture": {"fps": 50, "scale_width": 480},
        "session": {"min_game_frames": 120},
    }
    assert template["capture"]["scale_width"] == 720  # inputs untouched
    assert sc.prune({"capture": {"fps": None}, "log": {"level": "info"}}) == {
        "log": {"level": "info"}
    }
    # Key order does not change the revision; values do.
    assert sc.revision({"a": 1, "b": {"c": 2}}) == sc.revision({"b": {"c": 2}, "a": 1})
    assert sc.revision({"a": 1}) != sc.revision({"a": 2})
    assert 0 <= sc.revision(merged) < 2**48
    assert sc.get_path(merged, "capture.fps") == 50
    assert sc.get_path(merged, "capture.nope") is None


def test_needs_send() -> None:
    assert sc.needs_send(5, None, None)
    assert sc.needs_send(5, 4, "applied")
    assert not sc.needs_send(5, 5, "applied")
    assert not sc.needs_send(5, 5, "pending")
    assert not sc.needs_send(5, 5, "rejected")  # would only be rejected again
    assert sc.needs_send(5, 5, "none")


# ---------------------------------------------------------------- service


class _FakeDb:
    is_ready = True

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[None]:
        yield None


def _report(rev: int | None, state: str) -> ConfigReportPayload:
    return ConfigReportPayload(station="station-1", rev=rev, state=state)


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch) -> tuple[StationConfigService, LiveHub, list[Any]]:
    desired: dict[str, Any] = {"capture": {"scale_width": 480}}

    async def fake_desired(_session: Any, _station: str) -> tuple[Any, Any]:
        return desired, desired

    monkeypatch.setattr(service_mod, "desired_for", fake_desired)
    hub = LiveHub()
    sent: list[Any] = []

    async def sink(station: str, command: dict[str, Any]) -> bool:
        sent.append((station, command))
        return True

    svc = StationConfigService(_FakeDb(), hub, sink)  # type: ignore[arg-type]
    return svc, hub, sent


async def test_sync_sends_until_the_station_holds_the_set(
    setup: tuple[StationConfigService, LiveHub, list[Any]],
) -> None:
    svc, hub, sent = setup
    rev = sc.revision({"capture": {"scale_width": 480}})
    # Not heard yet / an old station without the config topic: nothing.
    assert await svc.sync("station-1") is None
    with pytest.raises(StationConfigError, match=r"0.3.0"):
        await svc.sync("station-1", force=True)

    hub.update_status("station-1", StatusPayload.model_validate_json(dumps(STATUS)))
    hub.update_config("station-1", _report(None, "none"))
    command = await svc.sync("station-1")
    assert command == {
        "type": "station_config",
        "op": "set",
        "rev": rev,
        "values": {"capture": {"scale_width": 480}},
    }
    assert sent == [("station-1", command)]
    # A repeat within the resend window is suppressed ...
    assert await svc.sync("station-1") is None
    # ... and once the station holds it, nothing goes out even when forced
    # through the window check.
    hub.update_config("station-1", _report(rev, "applied"))
    svc._sent.clear()
    assert await svc.sync("station-1") is None
    # A rejected revision is not retried automatically, only on demand.
    hub.update_config("station-1", _report(rev, "rejected"))
    assert await svc.sync("station-1") is None
    assert await svc.sync("station-1", force=True) is not None


async def test_offline_station_is_skipped(
    setup: tuple[StationConfigService, LiveHub, list[Any]],
) -> None:
    svc, hub, sent = setup
    hub.update_config("station-1", _report(None, "none"))
    hub.update_status(
        "station-1", StatusPayload.model_validate_json(dumps({**STATUS, "state": "offline"}))
    )
    hub.station("station-1").live_at = None
    assert await svc.sync("station-1") is None
    with pytest.raises(StationConfigError) as err:
        await svc.sync("station-1", force=True)
    assert err.value.code == "offline"
    assert sent == []


async def test_config_report_reaches_hub_and_listener() -> None:
    from nestris_ltm.ingest.service import IngestService

    hub = LiveHub()
    ingest = IngestService(None, hub, None, None)  # type: ignore[arg-type]
    seen: list[str] = []

    async def listener(station: str) -> None:
        seen.append(station)

    ingest.config_listener = listener
    report = {"station": "station-1", "rev": 7, "state": "applied", "values": {}, "effective": {}}
    await ingest.handle_message(
        "retroverse/nestris/station-1/config", dumps(report).encode(), "retroverse/nestris"
    )
    for task in list(ingest._background):
        await task
    assert seen == ["station-1"]
    snap = hub.snapshot()[0]
    assert snap["config"] == {"rev": 7, "state": "applied", "error": None}
