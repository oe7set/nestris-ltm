"""Updates of NestrisLTM from GitHub releases (docs/UPDATES.md).

Checking runs by itself (1 minute after start, then every
``updates.check_interval_h``); installing is always an admin's click:

1. download ``SHA256SUMS.txt``, its signature and the installer into
   ``<data_dir>/updates/<version>/``;
2. verify the signature (release key in ``core/releases.py``), then the
   installer's SHA-256;
3. back up the database with ``pg_dump`` into ``<data_dir>/backups/``;
4. start the installer (``/SILENT /update=1``; Windows asks for admin rights)
   and quit, the installer restarts NestrisLTM.

Running games block the install unless the admin confirms. Installing only
works in the installed (frozen) app; a development checkout can check.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog

from nestris_ltm import __version__
from nestris_ltm.config import Settings
from nestris_ltm.core.releases import RELEASE_PUBLIC_KEYS, Version, parse_sums, verify_signature

log = structlog.get_logger(__name__)

FIRST_CHECK_DELAY_S = 60.0
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024
BACKUPS_KEPT = 10
BACKUP_TIMEOUT_S = 900.0
SUMS_FILE = "SHA256SUMS.txt"
LIVE_GAME_STATES = {"in_game", "paused"}
LIVE_RECENT = timedelta(seconds=10)


class UpdateError(Exception):
    """An update step failed; ``code`` is stable for the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int


@dataclass(frozen=True)
class Release:
    tag: str
    version: Version
    prerelease: bool
    notes: str
    published_at: str | None
    html_url: str
    assets: dict[str, Asset] = field(default_factory=dict)

    @property
    def installer_name(self) -> str:
        """The release's installer: ``NestrisLTM-Setup-<version>.exe`` in the
        tag's spelling (``0.2.0b1`` and ``0.2.0-beta.1`` name the same version)."""
        exact = f"NestrisLTM-Setup-{self.version}.exe"
        if exact in self.assets:
            return exact
        for name in self.assets:
            if name.startswith("NestrisLTM-Setup-") and name.endswith(".exe"):
                found = Version.parse(name.removeprefix("NestrisLTM-Setup-").removesuffix(".exe"))
                if found == self.version:
                    return name
        return exact

    @property
    def installable(self) -> bool:
        return (
            self.installer_name in self.assets
            and SUMS_FILE in self.assets
            and (SUMS_FILE + ".sig" in self.assets)
        )

    def summary(self) -> dict[str, Any]:
        return {
            "version": str(self.version),
            "tag": self.tag,
            "prerelease": self.prerelease,
            "published_at": self.published_at,
            "notes": self.notes,
            "url": self.html_url,
            "installable": self.installable,
        }


class GitHubReleases:
    """The releases of one GitHub repository (unauthenticated by default)."""

    API = "https://api.github.com"

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.owner = owner
        self.repo = repo
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"NestrisLTM/{__version__}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            headers=headers, transport=transport, timeout=30.0, follow_redirects=True
        )
        self._etag: str | None = None
        self._cached: list[Release] = []

    async def close(self) -> None:
        await self._client.aclose()

    async def list(self) -> list[Release]:
        """Published releases, newest version first (drafts dropped)."""
        headers = {"If-None-Match": self._etag} if self._etag else {}
        r = await self._client.get(
            f"{self.API}/repos/{self.owner}/{self.repo}/releases",
            params={"per_page": 30},
            headers=headers,
        )
        if r.status_code == 304:  # unchanged: does not count against the rate limit
            return self._cached
        if r.status_code == 404:
            raise UpdateError("not_found", f"github.com/{self.owner}/{self.repo} not found")
        if r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0":
            raise UpdateError("rate_limited", "GitHub rate limit reached, try again later")
        r.raise_for_status()
        releases = []
        for item in r.json():
            if item.get("draft"):
                continue
            version = Version.parse(str(item.get("tag_name", "")))
            if version is None:
                continue
            assets = {
                a["name"]: Asset(a["name"], a["browser_download_url"], int(a.get("size", 0)))
                for a in item.get("assets", [])
            }
            releases.append(
                Release(
                    tag=item["tag_name"],
                    version=version,
                    prerelease=bool(item.get("prerelease")) or version.is_prerelease,
                    notes=str(item.get("body") or ""),
                    published_at=item.get("published_at"),
                    html_url=str(item.get("html_url") or ""),
                    assets=assets,
                )
            )
        releases.sort(key=lambda rel: rel.version, reverse=True)
        self._etag = r.headers.get("etag")
        self._cached = releases
        return releases

    async def fetch(self, url: str, max_bytes: int = 1024 * 1024) -> bytes:
        r = await self._client.get(url)
        r.raise_for_status()
        if len(r.content) > max_bytes:
            raise UpdateError("too_large", f"{url} is larger than expected")
        return r.content

    async def download(
        self, url: str, dest: Path, progress: Callable[[int, int], None] | None = None
    ) -> Path:
        tmp = dest.with_suffix(dest.suffix + ".part")
        async with self._client.stream("GET", url) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            done = 0
            with tmp.open("wb") as fh:
                async for chunk in r.aiter_bytes(256 * 1024):
                    done += len(chunk)
                    if done > MAX_DOWNLOAD_BYTES:
                        raise UpdateError("too_large", "download larger than 500 MB")
                    fh.write(chunk)
                    if progress:
                        progress(done, total)
        tmp.replace(dest)
        return dest


# ---------------------------------------------------------------- database backup


def find_pg_tool(name: str, configured_pg_dump: str = "") -> str | None:
    """A PostgreSQL client tool (``pg_dump``, ``pg_restore``): next to the
    configured pg_dump, from the newest local PostgreSQL install, or on PATH."""
    exe_name = f"{name}.exe" if sys.platform == "win32" else name
    if configured_pg_dump:
        candidate = Path(configured_pg_dump)
        if name != "pg_dump":
            candidate = candidate.with_name(exe_name)
        return str(candidate) if candidate.is_file() else None
    if sys.platform == "win32":
        import winreg

        best: tuple[Version, str] | None = None
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\PostgreSQL\Installations"
            ) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as inst:
                        base, _ = winreg.QueryValueEx(inst, "Base Directory")
                        try:
                            ver_text, _ = winreg.QueryValueEx(inst, "Version")
                        except OSError:
                            ver_text = "0.0"
                        exe = Path(base) / "bin" / exe_name
                        parts = [*str(ver_text).split("."), "0", "0"][:3]
                        ver = Version.parse(".".join(p if p.isdigit() else "0" for p in parts))
                        if exe.is_file() and ver and (best is None or ver > best[0]):
                            best = (ver, str(exe))
        except OSError:
            pass
        if best:
            return best[1]
    return shutil.which(name)


def find_pg_dump(configured: str = "") -> str | None:
    """pg_dump of the configured path, the local PostgreSQL install or PATH."""
    return find_pg_tool("pg_dump", configured)


async def run_pg_dump(settings: Settings, target: Path) -> Path:
    """``pg_dump -Fc`` of NestrisLTM's database into ``target``."""
    exe = find_pg_dump(settings.updates.pg_dump)
    if exe is None:
        raise UpdateError(
            "no_pg_dump", "pg_dump not found (PostgreSQL client tools; config updates.pg_dump)"
        )
    db = settings.database
    env = {**os.environ, "PGPASSWORD": db.password.get_secret_value(), "PGCONNECT_TIMEOUT": "10"}
    args = [
        exe, "-h", db.host, "-p", str(db.port), "-U", db.user, "-d", db.name,
        "-Fc", "--no-password", "-f", str(target),
    ]  # fmt: skip

    def dump() -> tuple[int, str, bool]:
        # A thread with subprocess.run, not asyncio subprocesses: on Windows the
        # app runs a SelectorEventLoop (aiomqtt), which cannot spawn processes.
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                args,
                env=env,
                capture_output=True,
                timeout=BACKUP_TIMEOUT_S,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return -1, "pg_dump timed out", False
        written = target.is_file() and target.stat().st_size > 0
        if proc.returncode != 0 or not written:
            target.unlink(missing_ok=True)
        return proc.returncode, proc.stderr.decode("utf-8", "replace").strip()[-300:], written

    code, detail, written = await asyncio.to_thread(dump)
    if code != 0 or not written:
        raise UpdateError("backup_failed", f"pg_dump failed: {detail or code}")
    return target


def prune_backups(directory: Path, keep: int = BACKUPS_KEPT) -> None:
    dumps = sorted(
        directory.glob("nestrisltm-*.dump"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for old in dumps[keep:]:
        with contextlib.suppress(OSError):
            old.unlink()


def start_installer(path: Path, args: str) -> None:
    """Run the installer through ShellExecute, so Windows shows the UAC prompt
    (a plain CreateProcess fails with "elevation required")."""
    if sys.platform != "win32":
        raise UpdateError("unsupported", "installing updates is only supported on Windows")
    os.startfile(str(path), "open", args)


def running_live_games(stations: list[Any], now: datetime | None = None) -> int:
    """Stations currently playing a game (recent live data, in game or paused)."""
    now = now or datetime.now(UTC)
    count = 0
    for st in stations:
        live, at = getattr(st, "live", None), getattr(st, "live_at", None)
        if live is None or at is None or now - at > LIVE_RECENT:
            continue
        if live.game_state in LIVE_GAME_STATES:
            count += 1
    return count


# ---------------------------------------------------------------- service

Backup = Callable[[Settings, Path], Awaitable[Path]]
Launcher = Callable[[Path, str], None]


class UpdateService:
    def __init__(
        self,
        settings: Settings,
        *,
        live_games: Callable[[], int] = lambda: 0,
        request_quit: Callable[[], None] = lambda: None,
        github: GitHubReleases | None = None,
        backup: Backup = run_pg_dump,
        launcher: Launcher = start_installer,
        frozen: bool | None = None,
        current_version: str = __version__,
        public_keys: tuple[str, ...] = RELEASE_PUBLIC_KEYS,
    ) -> None:
        cfg = settings.updates
        self.settings = settings
        self.github = github or GitHubReleases(cfg.owner, cfg.repo, cfg.token.get_secret_value())
        self.live_games = live_games
        self.request_quit = request_quit
        self._backup = backup
        self._launcher = launcher
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self.current = Version.parse(current_version) or Version(0, 0, 0)
        self.public_keys = public_keys
        self.releases: list[Release] = []
        self.latest: Release | None = None
        self.last_check: datetime | None = None
        self.check_error: str | None = None
        self.status = (
            "idle"  # idle, checking, downloading, verifying, backing_up, installing, error
        )
        self.status_detail: str | None = None
        self.progress: float | None = None
        self.last_backup: str | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ checking

    def _candidates(self) -> list[Release]:
        beta = self.settings.updates.channel == "beta"
        return [r for r in self.releases if beta or not r.prerelease]

    async def check(self) -> dict[str, Any]:
        if self.status == "idle" or self.status == "error":
            self.status = "checking"
        try:
            self.releases = await self.github.list()
            candidates = self._candidates()
            self.latest = candidates[0] if candidates else None
            self.check_error = None
        except UpdateError as exc:
            self.check_error = exc.message
        except httpx.HTTPError as exc:
            # Offline at the venue is normal; say so quietly.
            self.check_error = f"no connection to GitHub ({type(exc).__name__})"
        finally:
            self.last_check = datetime.now(UTC)
            if self.status == "checking":
                self.status = "idle"
        if self.update_available:
            log.info("update available", current=str(self.current), latest=str(self.latest.version))  # type: ignore[union-attr]
        return self.state()

    @property
    def update_available(self) -> bool:
        return self.latest is not None and self.latest.version > self.current

    async def run(self) -> None:
        """Background checks while ``updates.enabled``."""
        await asyncio.sleep(FIRST_CHECK_DELAY_S)
        while True:
            if self.settings.updates.enabled:
                await self.check()
            await asyncio.sleep(self.settings.updates.check_interval_h * 3600)

    def state(self) -> dict[str, Any]:
        cfg = self.settings.updates
        return {
            "current": str(self.current),
            "latest": self.latest.summary() if self.latest else None,
            "update_available": self.update_available,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "check_error": self.check_error,
            "status": self.status,
            "status_detail": self.status_detail,
            "progress": self.progress,
            "last_backup": self.last_backup,
            "can_install": self.frozen and sys.platform == "win32",
            "enabled": cfg.enabled,
            "channel": cfg.channel,
            "source": f"github.com/{cfg.owner}/{cfg.repo}",
            "live_games": self.live_games(),
        }

    def release_list(self) -> list[dict[str, Any]]:
        out = []
        for rel in self._candidates():
            item = rel.summary()
            item["is_current"] = rel.version == self.current
            item["is_downgrade"] = rel.version < self.current
            out.append(item)
        return out

    # ------------------------------------------------------------ installing

    def _set(self, status: str, detail: str | None = None, progress: float | None = None) -> None:
        self.status = status
        self.status_detail = detail
        self.progress = progress

    async def install(
        self, version: str, *, confirm_running: bool = False, skip_backup: bool = False
    ) -> dict[str, Any]:
        if not self.frozen:
            raise UpdateError(
                "dev", "updates install only in the installed app (not a source checkout)"
            )
        if self._lock.locked():
            raise UpdateError("busy", "an update is already in progress")
        live = self.live_games()
        if live and not confirm_running:
            raise UpdateError("games_running", f"{live} game(s) running")
        async with self._lock:
            try:
                if not self.releases:
                    await self.check()
                target = Version.parse(version)
                release = next((r for r in self.releases if r.version == target), None)
                if release is None:
                    raise UpdateError("unknown_version", f"release {version} not found")
                if not release.installable:
                    raise UpdateError(
                        "not_installable", f"release {version} has no signed installer"
                    )
                installer = await self._download_verified(release)
                if not skip_backup:
                    self._set("backing_up", "pg_dump")
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    backups = self.settings.data_dir / "backups"
                    name = f"nestrisltm-{stamp}-before-{release.version}.dump"
                    dump = await self._backup(self.settings, backups / name)
                    self.last_backup = str(dump)
                    prune_backups(backups)
                    log.info("database backed up", path=str(dump))
                self._set("installing", str(release.version))
                logfile = self.settings.data_dir / "updates" / f"install-{release.version}.log"
                args = f'/SILENT /SUPPRESSMSGBOXES /NORESTART /update=1 /LOG="{logfile}"'
                log.info(
                    "starting installer", version=str(release.version), installer=str(installer)
                )
                self._launcher(installer, args)
            except UpdateError as exc:
                self._set("error", exc.message)
                raise
            except Exception as exc:
                self._set("error", f"{type(exc).__name__}: {exc}")
                raise UpdateError("failed", str(exc)) from exc
        # Give the API response a moment, then leave so the installer can replace us.
        asyncio.get_running_loop().call_later(1.5, self.request_quit)
        return self.state()

    async def _download_verified(self, release: Release) -> Path:
        folder = self.settings.data_dir / "updates" / str(release.version)
        folder.mkdir(parents=True, exist_ok=True)
        self._set("downloading", SUMS_FILE, 0.0)
        sums_bytes = await self.github.fetch(release.assets[SUMS_FILE].url)
        signature = (await self.github.fetch(release.assets[SUMS_FILE + ".sig"].url)).decode(
            "ascii", "replace"
        )
        self._set("verifying", "signature")
        if not verify_signature(sums_bytes, signature, self.public_keys):
            raise UpdateError("bad_signature", "SHA256SUMS.txt is not signed by the release key")
        expected = parse_sums(sums_bytes.decode("utf-8", "replace")).get(release.installer_name)
        if expected is None:
            raise UpdateError("bad_checksum", f"{release.installer_name} is not in SHA256SUMS.txt")

        asset = release.assets[release.installer_name]
        dest = folder / asset.name

        def progress(done: int, total: int) -> None:
            self.progress = round(done / total, 3) if total else None

        self._set("downloading", asset.name, 0.0)
        await self.github.download(asset.url, dest, progress)
        self._set("verifying", "sha256")
        digest = await asyncio.to_thread(_sha256, dest)
        if digest != expected:
            dest.unlink(missing_ok=True)
            raise UpdateError("bad_checksum", f"{asset.name}: checksum mismatch")
        return dest


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
