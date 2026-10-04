"""Devices: station/reader/terminal versions, the release cache, station updates."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nestris_ltm.config import load_settings
from nestris_ltm.core.releases import Version
from nestris_ltm.ingest.payloads import LivePayload, StatusPayload, UpdatePayload
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services.devices import DeviceUpdates, station_offers
from nestris_ltm.services.updates import Asset, Release, UpdateError

KEY = Ed25519PrivateKey.generate()
PUBLIC = base64.b64encode(
    KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
).decode()


def sign(data: bytes) -> str:
    return base64.b64encode(KEY.sign(data)).decode()


class FakeGitHub:
    def __init__(self) -> None:
        self.releases: dict[str, list[dict[str, Any]]] = {
            "nestris-core": [], "nestris-rfid-reader": [], "nestris-terminal": [],
        }  # fmt: skip
        self.files: dict[str, bytes] = {}
        self.downloads: list[str] = []

    def publish(self, repo: str, tag: str, files: dict[str, bytes], *,
                prerelease: bool = False, signature: str | None = None) -> None:  # fmt: skip
        sums = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in files.items())
        files = {**files, "SHA256SUMS.txt": sums.encode(),
                 "SHA256SUMS.txt.sig": (signature or sign(sums.encode())).encode()}  # fmt: skip
        base = f"https://github.com/oe7set/{repo}/releases/download/{tag}"
        for n, d in files.items():
            self.files[f"{base}/{n}"] = d
        self.releases[repo].insert(0, {
            "tag_name": tag, "draft": False, "prerelease": prerelease, "body": f"notes {tag}",
            "published_at": "2026-10-04T12:00:00Z", "html_url": f"https://github.com/x/{tag}",
            "assets": [{"name": n, "browser_download_url": f"{base}/{n}", "size": len(d)}
                       for n, d in files.items()],
        })  # fmt: skip

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        for repo, releases in self.releases.items():
            if url.endswith(f"/repos/oe7set/{repo}/releases"):
                return httpx.Response(200, json=releases)
        if url in self.files:
            self.downloads.append(url.rsplit("/", 1)[1])
            return httpx.Response(200, content=self.files[url])
        return httpx.Response(404)


def core_release(gh: FakeGitHub, tag: str, station: str, **kw: Any) -> None:
    gh.publish("nestris-core", tag, {
        f"nestris-station_{station}-1_amd64.deb": b"deb amd64 " + station.encode(),
        f"nestris-station_{station}-1_arm64.deb": b"deb arm64 " + station.encode(),
        f"nestris-cli-{tag}-linux-x64.zip": b"zip",
    }, **kw)  # fmt: skip


def reader_release(gh: FakeGitHub, version: str) -> None:
    manifest = {"chip": "esp32", "files": [
        {"kind": "app", "name": f"nestris-rfid-reader-{version}-esp32dev-app.bin", "offset": "0x10000"},
        {"kind": "factory", "name": f"nestris-rfid-reader-{version}-esp32dev.bin", "offset": "0x0"},
    ]}  # fmt: skip
    gh.publish("nestris-rfid-reader", f"v{version}", {
        f"nestris-rfid-reader-{version}-esp32dev.bin": b"factory",
        f"nestris-rfid-reader-{version}-esp32dev-app.bin": b"app",
        f"nestris-rfid-reader-{version}-manifest.json": json.dumps(manifest).encode(),
    })  # fmt: skip


def status(station: str, *, version: str = "0.2.0", reader_fw: str | None = "1.0.0",
           rfid: str = "ok") -> StatusPayload:  # fmt: skip
    return StatusPayload(state="online", station=station, name=station.title(), version=version,
                         rfid=rfid, reader_fw=reader_fw, reader_serial="B8D61A5DE9D4")  # fmt: skip


@pytest.fixture
def gh() -> FakeGitHub:
    g = FakeGitHub()
    core_release(g, "v0.1.0", "0.2.0")
    core_release(g, "v0.2.0", "0.2.1")
    core_release(g, "v0.2.1", "0.2.1")  # station unchanged in this release
    reader_release(g, "1.0.0")
    reader_release(g, "1.1.0")
    g.publish("nestris-terminal", "v0.2.0", {"RetroverseTerminal-Setup-0.2.0.exe": b"MZ"})
    return g


def make(
    tmp_path: Path, gh: FakeGitHub
) -> tuple[DeviceUpdates, LiveHub, list[tuple[str, dict[str, Any]]]]:
    hub = LiveHub()
    sent: list[tuple[str, dict[str, Any]]] = []

    async def sink(station: str, command: dict[str, Any]) -> bool:
        sent.append((station, command))
        return True

    service = DeviceUpdates(
        load_settings(tmp_path / "none.toml", data_dir=tmp_path), hub, sink,
        transport=httpx.MockTransport(gh), public_keys=(PUBLIC,),
    )  # fmt: skip
    return service, hub, sent


async def test_overview(tmp_path: Path, gh: FakeGitHub) -> None:
    service, hub, _ = make(tmp_path, gh)
    hub.update_status("station-1", status("station-1"))
    hub.update_status(
        "station-2", status("station-2", version="0.2.1", reader_fw=None, rfid="outdated")
    )
    service.note_terminal("terminal-eingang", "192.168.1.20", "0.1.0", "1.1.0")
    state = await service.check()
    assert state["latest"]["station"]["version"] == "0.2.1"
    assert state["latest"]["station"]["release"] == "v0.2.1"  # newest release with it
    assert state["latest"]["reader"]["version"] == "1.1.0"
    assert state["latest"]["terminal"]["version"] == "0.2.0"
    one, two = state["stations"]
    assert one["station_update"] and one["reader_update"]
    assert not two["station_update"] and two["reader_update"]  # old reader protocol
    [terminal] = state["terminals"]
    assert terminal["update"] and not terminal["reader_update"]
    assert [v["version"] for v in state["station_versions"]] == ["0.2.1", "0.2.0"]


def test_station_offers_parse_deb_names(gh: FakeGitHub) -> None:
    releases = [
        Release(
            item["tag_name"], Version.parse(item["tag_name"]), False, "", None, "",  # type: ignore[arg-type]
            {a["name"]: Asset(a["name"], a["browser_download_url"], 1) for a in item["assets"]},
        )
        for item in gh.releases["nestris-core"]
    ]  # fmt: skip
    offers = station_offers(releases)
    assert [(str(o.version), o.release.tag, o.arches) for o in offers] == [
        ("0.2.1", "v0.2.1", ("amd64", "arm64")),
        ("0.2.0", "v0.1.0", ("amd64", "arm64")),
    ]


async def test_update_station_caches_verified_files(tmp_path: Path, gh: FakeGitHub) -> None:
    service, hub, sent = make(tmp_path, gh)
    hub.update_status("station-1", status("station-1"))
    command = await service.update_station("station-1", "station", "0.2.1")
    assert command == {"type": "update", "target": "station", "release": "v0.2.1",
                       "version": "0.2.1", "mode": "app"}  # fmt: skip
    assert sent == [("station-1", command)]
    deb = service.cached_file("nestris-core", "v0.2.1", "nestris-station_0.2.1-1_arm64.deb")
    assert deb is not None and deb.read_bytes() == b"deb arm64 0.2.1"
    assert service.cached_file("nestris-core", "v0.2.1", "SHA256SUMS.txt.sig") is not None
    # Only what was asked for, and nothing outside the cache.
    assert service.cached_file("nestris-core", "v0.2.1", "nestris-cli-v0.2.1-linux-x64.zip") is None
    assert service.cached_file("nestris-core", "..", "SHA256SUMS.txt") is None
    assert service.cached_file("nestris-core", "v0.2.1", "../../config.toml") is None
    assert service.cached_file("nestris-ltm", "v0.2.1", "SHA256SUMS.txt") is None

    # A second request re-uses the verified files (only the checksum list again).
    gh.downloads.clear()
    await service.update_station("station-1", "station", "0.2.1")
    assert not any(d.endswith(".deb") for d in gh.downloads)

    await service.update_station("station-1", "reader", "1.1.0", factory=True)
    assert sent[-1][1]["mode"] == "factory" and sent[-1][1]["release"] == "v1.1.0"
    assert service.cached_file(
        "nestris-rfid-reader", "v1.1.0", "nestris-rfid-reader-1.1.0-esp32dev-app.bin"
    )


async def test_update_station_refusals(tmp_path: Path, gh: FakeGitHub) -> None:
    service, hub, sent = make(tmp_path, gh)
    with pytest.raises(UpdateError) as err:
        await service.update_station("station-9", "station", "0.2.1")
    assert err.value.code == "offline"
    hub.update_status("station-1", status("station-1"))
    hub.update_live(
        "station-1", LivePayload(game_state="in_game", score=1000, ts=datetime.now(UTC))
    )
    with pytest.raises(UpdateError) as err:
        await service.update_station("station-1", "station", "0.2.1")
    assert err.value.code == "games_running"
    hub.update_live("station-1", LivePayload(game_state="game_over", ts=datetime.now(UTC)))
    with pytest.raises(UpdateError) as err:
        await service.update_station("station-1", "station", "9.9.9")
    assert err.value.code == "unknown_version"
    assert sent == []


async def test_forged_release_is_not_cached(tmp_path: Path, gh: FakeGitHub) -> None:
    core_release(gh, "v0.3.0", "0.3.0", signature=base64.b64encode(b"\0" * 64).decode())
    service, hub, sent = make(tmp_path, gh)
    hub.update_status("station-1", status("station-1"))
    with pytest.raises(UpdateError) as err:
        await service.update_station("station-1", "station", "0.3.0")
    assert err.value.code == "bad_signature"
    assert sent == []
    assert service.cached_file("nestris-core", "v0.3.0", "SHA256SUMS.txt") is None


def test_update_progress_reaches_the_station_snapshot() -> None:
    hub = LiveHub()
    hub.update_update("station-1", UpdatePayload(
        station="station-1", target="reader", version="1.1.0", state="flashing",
        progress=0.4, ts=datetime.now(UTC),
    ))  # fmt: skip
    snap = hub.stations()[0].snapshot()
    assert snap["update"]["state"] == "flashing" and snap["update"]["progress"] == 0.4


@pytest.mark.db
async def test_device_api(tmp_path: Path, fresh_db_settings: Any, gh: FakeGitHub) -> None:
    from nestris_ltm.api.app import create_app
    from nestris_ltm.runtime import Runtime

    rt = Runtime(
        load_settings(tmp_path / "none.toml", database=fresh_db_settings, data_dir=tmp_path)
    )
    await rt.db.run_bootstrap()
    await rt.devices.close()
    sent: list[tuple[str, dict[str, Any]]] = []

    async def sink(station: str, command: dict[str, Any]) -> bool:
        sent.append((station, command))
        return True

    rt.devices = DeviceUpdates(rt.settings, rt.hub, sink, transport=httpx.MockTransport(gh),
                               public_keys=(PUBLIC,))  # fmt: skip
    rt.hub.update_status("station-1", status("station-1"))
    try:
        transport = httpx.ASGITransport(app=create_app(rt), client=("192.168.1.50", 5000))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            assert (await client.get("/api/devices")).status_code == 401
            h = {"X-NestrisLTM-Shell-Token": rt.shell_token}
            state = (await client.post("/api/devices/check", headers=h)).json()
            assert state["stations"][0]["station_update"]
            r = await client.post("/api/devices/stations/station-1/update", headers=h,
                                  json={"target": "station", "version": "0.2.1"})  # fmt: skip
            assert r.status_code == 200 and sent[0][1]["release"] == "v0.2.1"
            r = await client.post("/api/devices/stations/station-2/update", headers=h,
                                  json={"target": "station", "version": "0.2.1"})  # fmt: skip
            assert r.status_code == 409 and r.json()["detail"]["code"] == "offline"
            # The station's download (without a token: refused).
            url = "/api/stations/station-1/updates/nestris-core/v0.2.1/nestris-station_0.2.1-1_amd64.deb"
            assert (await client.get(url)).status_code == 401
            r = await client.get(url, headers=h)
            assert r.status_code == 200 and r.content == b"deb amd64 0.2.1"
            missing = url.replace("amd64.deb", "riscv.deb")
            assert (await client.get(missing, headers=h)).status_code == 404
    finally:
        await rt.devices.close()
        await rt.updates.github.close()
        await rt.db.dispose()


def test_mqtt_subscribes_to_update_progress(tmp_path: Path) -> None:
    from nestris_ltm.ingest.mqtt_client import MqttIngest

    settings = load_settings(tmp_path / "none.toml", data_dir=tmp_path)
    topics = [t for t, _ in MqttIngest(settings.mqtt, None).subscriptions()]  # type: ignore[arg-type]
    assert f"{settings.mqtt.topic_prefix}/+/update" in topics
