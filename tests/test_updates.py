"""Updates: version order, signed checksums, GitHub releases, the install flow."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nestris_ltm.config import load_settings
from nestris_ltm.core.releases import RELEASE_PUBLIC_KEYS, Version, parse_sums, verify_signature
from nestris_ltm.services.updates import (
    GitHubReleases,
    UpdateError,
    UpdateService,
    running_live_games,
)

KEY = Ed25519PrivateKey.generate()
PUBLIC = base64.b64encode(
    KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
).decode()
INSTALLER = b"MZ fake installer bytes" * 100


def sign(data: bytes, key: Ed25519PrivateKey = KEY) -> str:
    return base64.b64encode(key.sign(data)).decode()


# ---------------------------------------------------------------- pure helpers


def test_version_order() -> None:
    v = Version.parse
    order = [
        "0.9.9",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.1",
        "1.10.0",
    ]
    parsed = [v(x) for x in order]
    assert all(p is not None for p in parsed)
    assert sorted(parsed, key=lambda p: p._key()) == parsed  # type: ignore[union-attr]
    assert v("v1.2.3") == v("1.2.3") and str(v("v1.2.3-rc.1")) == "1.2.3-rc.1"
    assert v("1.2") is None and v("latest") is None
    assert v("1.0.0-rc1").is_prerelease  # type: ignore[union-attr]


def test_parse_sums() -> None:
    text = f"{'a' * 64}  NestrisLTM-Setup-1.0.0.exe\n{'B' * 64} *other.zip\nbroken line\n"
    assert parse_sums(text) == {"NestrisLTM-Setup-1.0.0.exe": "a" * 64, "other.zip": "b" * 64}


def test_signature_check() -> None:
    data = b"abc  file\n"
    assert verify_signature(data, sign(data), (PUBLIC,))
    assert not verify_signature(data + b"x", sign(data), (PUBLIC,))  # tampered
    assert not verify_signature(data, "not base64!!", (PUBLIC,))
    # The real release key does not accept a signature from another key.
    assert not verify_signature(data, sign(data), RELEASE_PUBLIC_KEYS)
    # Key rotation: any listed key may sign.
    other = Ed25519PrivateKey.generate()
    other_pub = base64.b64encode(
        other.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    assert verify_signature(data, sign(data, other), (PUBLIC, other_pub))


def test_running_live_games() -> None:
    now = datetime.now(UTC)
    st = lambda state, ago: SimpleNamespace(  # noqa: E731
        live=SimpleNamespace(game_state=state), live_at=now - timedelta(seconds=ago)
    )
    stations = [
        st("in_game", 1),
        st("paused", 2),
        st("game_over", 1),
        st("in_game", 60),
        SimpleNamespace(live=None, live_at=None),
    ]
    assert running_live_games(stations, now) == 2


# ---------------------------------------------------------------- fake GitHub


class FakeGitHub:
    """GitHub's releases API and asset downloads for one repository."""

    def __init__(self) -> None:
        self.releases: list[dict[str, Any]] = []
        self.files: dict[str, bytes] = {}
        self.requests: list[str] = []
        self.offline = False

    def add_release(
        self,
        version: str,
        *,
        prerelease: bool = False,
        draft: bool = False,
        installer: bytes = INSTALLER,
        sums_override: str | None = None,
        signature: str | None = None,
    ) -> None:
        name = f"NestrisLTM-Setup-{version}.exe"
        sums = sums_override or f"{hashlib.sha256(installer).hexdigest()}  {name}\n"
        sig = signature if signature is not None else sign(sums.encode())
        base = f"https://github.com/oe7set/nestris-ltm/releases/download/v{version}"
        self.files[f"{base}/{name}"] = installer
        self.files[f"{base}/SHA256SUMS.txt"] = sums.encode()
        self.files[f"{base}/SHA256SUMS.txt.sig"] = (sig + "\n").encode()
        self.releases.append(
            {
                "tag_name": f"v{version}",
                "draft": draft,
                "prerelease": prerelease,
                "body": f"Notes for {version}",
                "published_at": "2026-10-04T10:00:00Z",
                "html_url": f"https://github.com/oe7set/nestris-ltm/releases/tag/v{version}",
                "assets": [
                    {
                        "name": n,
                        "browser_download_url": f"{base}/{n}",
                        "size": len(self.files[f"{base}/{n}"]),
                    }
                    for n in (name, "SHA256SUMS.txt", "SHA256SUMS.txt.sig")
                ],
            }
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        self.requests.append(url)
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        if url.endswith("/repos/oe7set/nestris-ltm/releases"):
            etag = f'"{len(self.releases)}"'
            if request.headers.get("if-none-match") == etag:
                return httpx.Response(304)
            return httpx.Response(200, json=self.releases, headers={"etag": etag})
        if url in self.files:
            return httpx.Response(200, content=self.files[url])
        return httpx.Response(404)


@pytest.fixture
def gh() -> FakeGitHub:
    return FakeGitHub()


def make_service(
    tmp_path: Path, gh: FakeGitHub, *, current: str = "1.0.0", frozen: bool = True, **kwargs: Any
) -> tuple[UpdateService, dict[str, Any]]:
    settings = load_settings(tmp_path / "none.toml", data_dir=tmp_path)
    calls: dict[str, Any] = {"launched": [], "backups": [], "quit": 0}

    async def backup(_settings: Any, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PGDMP")
        calls["backups"].append(target)
        return target

    def quit_() -> None:
        calls["quit"] += 1

    service = UpdateService(
        settings,
        github=GitHubReleases("oe7set", "nestris-ltm", transport=httpx.MockTransport(gh)),
        backup=backup,
        launcher=lambda path, args: calls["launched"].append((path, args)),
        request_quit=quit_,
        frozen=frozen,
        current_version=current,
        public_keys=(PUBLIC,),
        **kwargs,
    )
    return service, calls


# ---------------------------------------------------------------- checking


async def test_check_finds_the_newest_stable_release(tmp_path: Path, gh: FakeGitHub) -> None:
    gh.add_release("1.0.0")
    gh.add_release("1.1.0")
    gh.add_release("1.2.0-rc.1", prerelease=True)
    gh.add_release("2.0.0", draft=True)
    service, _ = make_service(tmp_path, gh)
    state = await service.check()
    assert state["update_available"] is True
    assert state["latest"]["version"] == "1.1.0" and state["latest"]["installable"]
    assert [r["version"] for r in service.release_list()] == ["1.1.0", "1.0.0"]
    assert service.release_list()[1]["is_current"] is True

    service.settings.updates.channel = "beta"
    await service.check()  # unchanged list: answered with 304 from the ETag
    assert service.latest is not None and str(service.latest.version) == "1.2.0-rc.1"


async def test_check_offline_is_quiet(tmp_path: Path, gh: FakeGitHub) -> None:
    gh.offline = True
    service, _ = make_service(tmp_path, gh)
    state = await service.check()
    assert state["update_available"] is False
    assert "no connection" in state["check_error"] and state["last_check"] is not None
    assert state["status"] == "idle"


async def test_up_to_date(tmp_path: Path, gh: FakeGitHub) -> None:
    gh.add_release("1.0.0")
    service, _ = make_service(tmp_path, gh, current="1.0.0")
    assert (await service.check())["update_available"] is False


# ---------------------------------------------------------------- installing


async def test_install_downloads_verifies_backs_up_and_launches(
    tmp_path: Path, gh: FakeGitHub
) -> None:
    gh.add_release("1.1.0")
    service, calls = make_service(tmp_path, gh)
    state = await service.install("1.1.0")
    assert state["status"] == "installing"
    installer, args = calls["launched"][0]
    assert installer == tmp_path / "updates" / "1.1.0" / "NestrisLTM-Setup-1.1.0.exe"
    assert installer.read_bytes() == INSTALLER
    assert "/SILENT" in args and "/update=1" in args and "/LOG=" in args
    assert len(calls["backups"]) == 1 and "before-1.1.0" in calls["backups"][0].name
    await asyncio.sleep(1.7)
    assert calls["quit"] == 1  # the app leaves so the installer can replace it


async def test_forged_signature_is_refused(tmp_path: Path, gh: FakeGitHub) -> None:
    attacker = Ed25519PrivateKey.generate()
    evil = b"evil installer"
    sums = f"{hashlib.sha256(evil).hexdigest()}  NestrisLTM-Setup-1.1.0.exe\n"
    gh.add_release(
        "1.1.0", installer=evil, sums_override=sums, signature=sign(sums.encode(), attacker)
    )
    service, calls = make_service(tmp_path, gh)
    with pytest.raises(UpdateError) as err:
        await service.install("1.1.0")
    assert err.value.code == "bad_signature"
    assert calls["launched"] == [] and calls["backups"] == []
    assert service.state()["status"] == "error"


async def test_checksum_mismatch_is_refused(tmp_path: Path, gh: FakeGitHub) -> None:
    # Correctly signed list, but the uploaded installer is something else.
    sums = f"{hashlib.sha256(b'the real one').hexdigest()}  NestrisLTM-Setup-1.1.0.exe\n"
    gh.add_release("1.1.0", installer=b"swapped", sums_override=sums)
    service, calls = make_service(tmp_path, gh)
    with pytest.raises(UpdateError) as err:
        await service.install("1.1.0")
    assert err.value.code == "bad_checksum" and calls["launched"] == []
    assert not (tmp_path / "updates" / "1.1.0" / "NestrisLTM-Setup-1.1.0.exe").exists()


async def test_running_games_need_confirmation(tmp_path: Path, gh: FakeGitHub) -> None:
    gh.add_release("1.1.0")
    service, calls = make_service(tmp_path, gh, live_games=lambda: 2)
    with pytest.raises(UpdateError) as err:
        await service.install("1.1.0")
    assert err.value.code == "games_running" and calls["launched"] == []
    await service.install("1.1.0", confirm_running=True, skip_backup=True)
    assert len(calls["launched"]) == 1 and calls["backups"] == []


async def test_install_guards(tmp_path: Path, gh: FakeGitHub) -> None:
    gh.add_release("1.1.0")
    dev, _ = make_service(tmp_path, gh, frozen=False)
    with pytest.raises(UpdateError) as err:
        await dev.install("1.1.0")
    assert err.value.code == "dev"
    service, _ = make_service(tmp_path, gh)
    with pytest.raises(UpdateError) as err:
        await service.install("9.9.9")
    assert err.value.code == "unknown_version"


async def test_downgrade_is_possible(tmp_path: Path, gh: FakeGitHub) -> None:
    gh.add_release("0.9.0")
    gh.add_release("1.0.0")
    service, calls = make_service(tmp_path, gh, current="1.0.0")
    await service.check()
    older = next(r for r in service.release_list() if r["version"] == "0.9.0")
    assert older["is_downgrade"] is True
    await service.install("0.9.0")
    assert calls["launched"][0][0].name == "NestrisLTM-Setup-0.9.0.exe"


# ---------------------------------------------------------------- integration


def test_version_matches_pyproject() -> None:
    # The updater compares against __version__; the release workflow checks
    # the tag against pyproject.toml. Both must agree.
    import tomllib

    from nestris_ltm import __version__

    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text("utf-8"))
    assert pyproject["project"]["version"] == __version__


@pytest.mark.db
async def test_pg_dump_backup_of_a_real_database(tmp_path: Path, db: Any) -> None:
    from nestris_ltm.services.updates import find_pg_dump, run_pg_dump

    if find_pg_dump() is None:
        pytest.skip("no PostgreSQL client tools on this machine")
    settings = load_settings(tmp_path / "none.toml", data_dir=tmp_path, database=db.settings)
    dump = await run_pg_dump(settings, tmp_path / "backups" / "nestrisltm-test.dump")
    assert dump.read_bytes()[:5] == b"PGDMP"  # pg_dump custom format


@pytest.mark.db
async def test_update_api(tmp_path: Path, fresh_db_settings: Any, gh: FakeGitHub) -> None:
    from nestris_ltm.api.app import create_app
    from nestris_ltm.runtime import Runtime

    gh.add_release("9.0.0")
    rt = Runtime(
        load_settings(tmp_path / "none.toml", database=fresh_db_settings, data_dir=tmp_path)
    )
    await rt.db.run_bootstrap()
    rt.updates.github = GitHubReleases("oe7set", "nestris-ltm", transport=httpx.MockTransport(gh))
    rt.updates.public_keys = (PUBLIC,)
    rt.updates.frozen = False  # a source checkout: checking works, installing does not
    try:
        transport = httpx.ASGITransport(app=create_app(rt), client=("192.168.1.50", 5000))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as remote:
            assert (await remote.get("/api/updates")).status_code == 401
            headers = {"X-NestrisLTM-Shell-Token": rt.shell_token}
            state = (await remote.post("/api/updates/check", headers=headers)).json()
            assert state["update_available"] and state["latest"]["version"] == "9.0.0"
            assert state["can_install"] is False
            releases = (await remote.get("/api/updates/releases", headers=headers)).json()
            assert [r["version"] for r in releases] == ["9.0.0"]
            r = await remote.post(
                "/api/updates/install", headers=headers, json={"version": "9.0.0"}
            )
            assert r.status_code == 400 and r.json()["detail"]["code"] == "dev"
    finally:
        await rt.updates.github.close()
        await rt.db.dispose()
