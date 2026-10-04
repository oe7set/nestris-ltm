"""Devices of the tournament network and their updates (docs/UPDATES.md, U4).

- **Stations** report ``version``, ``reader_fw`` and ``reader_serial`` in
  their MQTT status and update progress on ``<base>/update``.
- **Terminals** send ``X-Terminal-Version`` / ``X-Reader-Firmware`` with
  their API calls (:meth:`DeviceUpdates.note_terminal`).
- The newest releases come from GitHub: ``nestris-core`` (station packages
  ``nestris-station_<v>[-<rev>]_<arch>.deb``), ``nestris-rfid-reader`` and
  ``nestris-terminal``.

Station updates: NestrisLTM downloads the release files into
``<data_dir>/release-cache/<repo>/<tag>/`` and verifies them (stations
usually have no internet), then publishes the ``update`` command on
``<prefix>/<station>/cmd``. The station fetches the files from
``/api/stations/<station>/updates/<repo>/<tag>/<file>`` and verifies the
signature again itself, so a compromised host cannot push foreign packages.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog

from nestris_ltm.config import Settings
from nestris_ltm.core.releases import RELEASE_PUBLIC_KEYS, Version, parse_sums, verify_signature
from nestris_ltm.live.hub import LiveHub
from nestris_ltm.services.updates import (
    FIRST_CHECK_DELAY_S,
    LIVE_GAME_STATES,
    SUMS_FILE,
    GitHubReleases,
    Release,
    UpdateError,
)

log = structlog.get_logger(__name__)

STATION_REPO = "nestris-core"
READER_REPO = "nestris-rfid-reader"
TERMINAL_REPO = "nestris-terminal"
REPOS = (STATION_REPO, READER_REPO, TERMINAL_REPO)
SERVED_REPOS = (STATION_REPO, READER_REPO)

DEB_RE = re.compile(
    r"^nestris-station_(?P<version>\d+\.\d+\.\d+[0-9A-Za-z.+~]*?)(?:-(?P<rev>\d+))?_(?P<arch>[a-z0-9]+)\.deb$"
)
READER_MANIFEST_RE = re.compile(r"^nestris-rfid-reader-(?P<version>.+)-manifest\.json$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]{0,120}$")
TERMINAL_FORGET = timedelta(days=2)

CommandSink = Callable[[str, dict[str, Any]], Awaitable[bool]]


@dataclass
class TerminalSeen:
    name: str
    address: str | None
    version: str | None
    reader_fw: str | None
    last_seen: datetime


@dataclass(frozen=True)
class Offer:
    """A version of the station package or the reader firmware in a release."""

    version: Version
    release: Release
    arches: tuple[str, ...] = ()

    def summary(self) -> dict[str, Any]:
        return {
            "version": str(self.version),
            "release": self.release.tag,
            "prerelease": self.release.prerelease,
            "published_at": self.release.published_at,
            "notes": self.release.notes,
            "url": self.release.html_url,
            "arches": list(self.arches),
        }


def station_offers(releases: list[Release]) -> list[Offer]:
    """Station package versions, newest first; a version shipped by several
    releases is offered from the newest one."""
    seen: dict[Version, Offer] = {}
    for rel in releases:  # newest release first
        arches: dict[Version, list[str]] = {}
        for name in rel.assets:
            m = DEB_RE.match(name)
            version = Version.parse(m["version"]) if m else None
            if m and version:
                arches.setdefault(version, []).append(m["arch"])
        for version, found in arches.items():
            if version not in seen:
                seen[version] = Offer(version, rel, tuple(sorted(found)))
    return sorted(seen.values(), key=lambda o: o.version, reverse=True)


def reader_offers(releases: list[Release]) -> list[Offer]:
    out: dict[Version, Offer] = {}
    for rel in releases:
        for name in rel.assets:
            m = READER_MANIFEST_RE.match(name)
            version = Version.parse(m["version"]) if m else None
            if version and version not in out:
                out[version] = Offer(version, rel)
    return sorted(out.values(), key=lambda o: o.version, reverse=True)


def _newer(latest: Offer | None, current: str | None) -> bool:
    have = Version.parse(current) if current else None
    return latest is not None and have is not None and latest.version > have


class DeviceUpdates:
    def __init__(
        self,
        settings: Settings,
        hub: LiveHub,
        command_sink: CommandSink | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        public_keys: tuple[str, ...] = RELEASE_PUBLIC_KEYS,
    ) -> None:
        cfg = settings.updates
        self.settings = settings
        self.hub = hub
        self.command_sink = command_sink
        self.public_keys = public_keys
        token = cfg.token.get_secret_value()
        self.github = {
            repo: GitHubReleases(cfg.owner, repo, token, transport=transport) for repo in REPOS
        }
        self.releases: dict[str, list[Release]] = {repo: [] for repo in REPOS}
        self.errors: dict[str, str | None] = dict.fromkeys(REPOS)
        self.last_check: datetime | None = None
        self.terminals: dict[str, TerminalSeen] = {}
        self._prepare_lock = asyncio.Lock()

    @property
    def cache_dir(self) -> Path:
        return self.settings.data_dir / "release-cache"

    async def close(self) -> None:
        for gh in self.github.values():
            await gh.close()

    # ------------------------------------------------------------ terminals

    def note_terminal(
        self, name: str, address: str | None, version: str | None, reader_fw: str | None
    ) -> None:
        self.terminals[name] = TerminalSeen(
            name, address, _clip(version), _clip(reader_fw), datetime.now(UTC)
        )

    # ------------------------------------------------------------ checking

    def _channel(self, repo: str) -> list[Release]:
        beta = self.settings.updates.channel == "beta"
        return [r for r in self.releases[repo] if beta or not r.prerelease]

    async def check(self) -> dict[str, Any]:
        for repo, gh in self.github.items():
            try:
                self.releases[repo] = await gh.list()
                self.errors[repo] = None
            except UpdateError as exc:
                self.errors[repo] = exc.message
            except httpx.HTTPError as exc:
                self.errors[repo] = f"no connection to GitHub ({type(exc).__name__})"
        self.last_check = datetime.now(UTC)
        return self.state()

    async def run(self) -> None:
        await asyncio.sleep(FIRST_CHECK_DELAY_S + 30)  # after NestrisLTM's own check
        while True:
            if self.settings.updates.enabled:
                await self.check()
            await asyncio.sleep(self.settings.updates.check_interval_h * 3600)

    def station_offers(self) -> list[Offer]:
        return station_offers(self._channel(STATION_REPO))

    def reader_offers(self) -> list[Offer]:
        return reader_offers(self._channel(READER_REPO))

    def latest_terminal(self) -> Release | None:
        releases = self._channel(TERMINAL_REPO)
        return releases[0] if releases else None

    # ------------------------------------------------------------ overview

    def state(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        stations, readers = self.station_offers(), self.reader_offers()
        latest_station = stations[0] if stations else None
        latest_reader = readers[0] if readers else None
        latest_terminal = self.latest_terminal()

        station_rows = []
        # Online stations first; old ones from earlier events below.
        for st in sorted(self.hub.stations(), key=lambda s: (not s.online(now), s.id)):
            status = st.status
            version = status.version if status else None
            reader_fw = status.reader_fw if status else None
            station_rows.append(
                {
                    "id": st.id,
                    "name": status.name if status else None,
                    "online": st.online(now),
                    "version": version,
                    "rfid": status.rfid if status else None,
                    "reader_fw": reader_fw,
                    "reader_serial": status.reader_serial if status else None,
                    "playing": self._playing(st.id, now),
                    "update": st.update.model_dump(mode="json") if st.update else None,
                    "station_update": _newer(latest_station, version),
                    # "outdated" = a reader with the old protocol: needs the factory image.
                    "reader_update": _newer(latest_reader, reader_fw)
                    or bool(status and status.rfid == "outdated" and latest_reader),
                }
            )

        for name in [n for n, t in self.terminals.items() if now - t.last_seen > TERMINAL_FORGET]:
            del self.terminals[name]
        terminal_rows = [
            {
                "name": t.name,
                "address": t.address,
                "version": t.version,
                "reader_fw": t.reader_fw,
                "last_seen": t.last_seen.isoformat(),
                "update": latest_terminal is not None
                and _newer(Offer(latest_terminal.version, latest_terminal), t.version),
                "reader_update": _newer(latest_reader, t.reader_fw),
            }
            for t in sorted(self.terminals.values(), key=lambda t: t.name)
        ]
        cfg = self.settings.updates
        return {
            "stations": station_rows,
            "terminals": terminal_rows,
            "latest": {
                "station": latest_station.summary() if latest_station else None,
                "reader": latest_reader.summary() if latest_reader else None,
                "terminal": latest_terminal.summary() if latest_terminal else None,
            },
            "station_versions": [o.summary() for o in stations[:10]],
            "reader_versions": [o.summary() for o in readers[:10]],
            "errors": self.errors,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "channel": cfg.channel,
            "owner": cfg.owner,
        }

    def _playing(self, station_id: str, now: datetime) -> bool:
        st = next((s for s in self.hub.stations() if s.id == station_id), None)
        if st is None or st.live is None or st.live_at is None:
            return False
        return now - st.live_at <= timedelta(seconds=10) and st.live.game_state in LIVE_GAME_STATES

    # ------------------------------------------------------------ release cache

    def _release_dir(self, repo: str, tag: str) -> Path:
        if repo not in SERVED_REPOS or not SAFE_NAME.match(tag):
            raise UpdateError("bad_request", "unknown repository or tag")
        return self.cache_dir / repo / tag

    async def prepare(self, repo: str, release: Release, wanted: list[str]) -> Path:
        """Download and verify ``wanted`` files of a release into the cache."""
        folder = self._release_dir(repo, release.tag)
        gh = self.github[repo]
        async with self._prepare_lock:
            folder.mkdir(parents=True, exist_ok=True)
            for name in (SUMS_FILE, SUMS_FILE + ".sig"):
                if name not in release.assets:
                    raise UpdateError("not_installable", f"release {release.tag} is not signed")
            sums_bytes = await gh.fetch(release.assets[SUMS_FILE].url)
            sig = await gh.fetch(release.assets[SUMS_FILE + ".sig"].url)
            if not verify_signature(sums_bytes, sig.decode("ascii", "replace"), self.public_keys):
                raise UpdateError(
                    "bad_signature", "SHA256SUMS.txt is not signed by the release key"
                )
            sums = parse_sums(sums_bytes.decode("utf-8", "replace"))
            for name in wanted:
                expected = sums.get(name)
                if expected is None or name not in release.assets:
                    raise UpdateError("not_installable", f"{name} is missing in {release.tag}")
                dest = folder / name
                if dest.is_file() and await asyncio.to_thread(_sha256, dest) == expected:
                    continue
                await gh.download(release.assets[name].url, dest)
                if await asyncio.to_thread(_sha256, dest) != expected:
                    dest.unlink(missing_ok=True)
                    raise UpdateError("bad_checksum", f"{name}: checksum mismatch")
            # Written last: a file is only served once the release is verified.
            (folder / (SUMS_FILE + ".sig")).write_bytes(sig)
            (folder / SUMS_FILE).write_bytes(sums_bytes)
        return folder

    def cached_file(self, repo: str, tag: str, name: str) -> Path | None:
        """A verified file of the cache (what the stations download)."""
        if not SAFE_NAME.match(name):
            return None
        try:
            folder = self._release_dir(repo, tag)
        except UpdateError:
            return None
        sums_path = folder / SUMS_FILE
        if not sums_path.is_file():
            return None
        listed = parse_sums(sums_path.read_text(encoding="utf-8", errors="replace"))
        if name not in listed and name not in (SUMS_FILE, SUMS_FILE + ".sig"):
            return None
        path = folder / name
        return path if path.is_file() else None

    # ------------------------------------------------------------ station updates

    async def update_station(
        self, station_id: str, target: str, version: str, *, factory: bool = False
    ) -> dict[str, Any]:
        st = next((s for s in self.hub.stations() if s.id == station_id), None)
        now = datetime.now(UTC)
        if st is None or not st.online(now):
            raise UpdateError("offline", f"station {station_id} is not online")
        if self._playing(station_id, now):
            raise UpdateError("games_running", "a game is running on this station")
        if self.command_sink is None:
            raise UpdateError("mqtt_offline", "no MQTT connection")
        if not any(self.releases.values()):
            await self.check()
        wanted_version = Version.parse(version)
        if target == "station":
            offer = next((o for o in self.station_offers() if o.version == wanted_version), None)
            if offer is None:
                raise UpdateError("unknown_version", f"station {version} not found")
            files = [n for n in offer.release.assets if (m := DEB_RE.match(n))
                     and Version.parse(m["version"]) == wanted_version]  # fmt: skip
            repo = STATION_REPO
        elif target == "reader":
            offer = next((o for o in self.reader_offers() if o.version == wanted_version), None)
            if offer is None:
                raise UpdateError("unknown_version", f"reader firmware {version} not found")
            v = str(offer.version)
            files = [f"nestris-rfid-reader-{v}-manifest.json",
                     f"nestris-rfid-reader-{v}-esp32dev-app.bin",
                     f"nestris-rfid-reader-{v}-esp32dev.bin"]  # fmt: skip
            repo = READER_REPO
        else:
            raise UpdateError("bad_request", f"unknown target {target!r}")
        await self.prepare(repo, offer.release, files)
        command = {
            "type": "update",
            "target": target,
            "release": offer.release.tag,
            "version": str(offer.version),
            "mode": "factory" if factory else "app",
        }
        if not await self.command_sink(station_id, command):
            raise UpdateError("mqtt_offline", "no MQTT connection")
        log.info("station update sent", station=station_id, **command)
        return command


def _clip(value: str | None) -> str | None:
    return value.strip()[:40] or None if value else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
