"""Database problem classification, retry behaviour and the problem API (no server needed)."""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.db import diagnosis
from nestris_ltm.db.diagnosis import MigrationFailedError, SchemaTooNewError, classify
from nestris_ltm.db.manager import DatabaseManager, DatabaseUnavailableError
from nestris_ltm.runtime import Runtime
from nestris_ltm.services import db_backup


@pytest.mark.parametrize(
    ("exc", "state", "permanent"),
    [
        (ConnectionRefusedError(10061, "refused"), diagnosis.UNREACHABLE, False),
        (TimeoutError(), diagnosis.UNREACHABLE, False),
        (socket.gaierror(11001, "getaddrinfo failed"), diagnosis.UNREACHABLE, False),
        (asyncpg.CannotConnectNowError("starting up"), diagnosis.UNREACHABLE, False),
        (asyncpg.InvalidPasswordError("password failed"), diagnosis.AUTH_FAILED, True),
        (
            asyncpg.InvalidAuthorizationSpecificationError("no pg_hba.conf entry"),
            diagnosis.AUTH_REJECTED,
            True,
        ),
        (
            asyncpg.InsufficientPrivilegeError("permission denied"),
            diagnosis.NO_CREATE_PERMISSION,
            True,
        ),
        (SchemaTooNewError("0099", "0011", "0.5.0"), diagnosis.SCHEMA_TOO_NEW, True),
        (
            MigrationFailedError("0009", "0011", ValueError("boom")),
            diagnosis.MIGRATION_FAILED,
            True,
        ),
        (ValueError("something else"), diagnosis.UNKNOWN, False),
    ],
)
def test_classify(exc: BaseException, state: str, permanent: bool) -> None:
    problem = classify(exc)
    assert problem.state == state
    assert problem.permanent is permanent
    assert problem.detail
    assert diagnosis.title(state)


def test_classify_unwraps_sqlalchemy_and_causes() -> None:
    inner = asyncpg.InvalidPasswordError("password authentication failed for user")
    wrapped = DBAPIError("connect", None, inner)
    assert classify(wrapped).state == diagnosis.AUTH_FAILED

    try:
        try:
            raise ConnectionRefusedError(10061, "refused")
        except OSError as exc:
            raise RuntimeError("outer") from exc
    except RuntimeError as outer:
        assert classify(outer).state == diagnosis.UNREACHABLE


def test_schema_too_new_carries_versions() -> None:
    problem = classify(SchemaTooNewError("0099", "0011", "0.5.0"))
    assert problem.extra == {"db_revision": "0099", "app_head": "0011", "migrated_by": "0.5.0"}
    assert "0.5.0" in problem.detail


def test_every_state_has_cli_text() -> None:
    states = [v for k, v in vars(diagnosis).items() if k.isupper() and isinstance(v, str)]
    for state in states:
        assert state in diagnosis.HINTS, state
        # The CLI prints to a cp1252 console on Windows.
        for text in [diagnosis.title(state), *diagnosis.steps(state)]:
            text.encode("cp1252")


# ---------------------------------------------------------------- manager


class FakeBootstrap:
    def __init__(self, errors: list[BaseException]) -> None:
        self.errors = errors
        self.calls = 0

    async def __call__(self, settings: DatabaseSettings, engine: AsyncEngine) -> None:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


async def test_manager_becomes_ready_after_transient_errors() -> None:
    fake = FakeBootstrap([ConnectionRefusedError(10061, "refused")])
    manager = DatabaseManager(DatabaseSettings(), bootstrap_fn=fake)
    try:
        assert manager.state == diagnosis.CONNECTING
        task = asyncio.create_task(manager.run_bootstrap(max_backoff_s=0.01))
        assert await manager.wait_ready(within_s=5)
        await task
        assert manager.state == diagnosis.READY
        assert manager.problem is None
        assert fake.calls == 2
        assert manager.attempts == 2
    finally:
        await manager.dispose()


async def test_manager_permanent_problem_waits_for_retry_now() -> None:
    fake = FakeBootstrap([asyncpg.InvalidPasswordError("password failed")])
    manager = DatabaseManager(DatabaseSettings(), bootstrap_fn=fake)
    task = asyncio.create_task(manager.run_bootstrap(permanent_retry_s=3600))
    try:
        for _ in range(100):
            if manager.problem is not None:
                break
            await asyncio.sleep(0.01)
        assert manager.state == diagnosis.AUTH_FAILED
        assert manager.next_retry_at is not None
        assert not await manager.wait_ready(within_s=0.1)
        with pytest.raises(DatabaseUnavailableError) as info:
            async with manager.session():
                pass
        assert info.value.state == diagnosis.AUTH_FAILED

        manager.retry_now()
        assert await manager.wait_ready(within_s=5)
        assert manager.state == diagnosis.READY
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await manager.dispose()


async def test_manager_reconfigure_swaps_settings() -> None:
    fake = FakeBootstrap([asyncpg.InvalidPasswordError("password failed")])
    manager = DatabaseManager(DatabaseSettings(), bootstrap_fn=fake)
    task = asyncio.create_task(manager.run_bootstrap(permanent_retry_s=3600))
    try:
        for _ in range(100):
            if manager.problem is not None:
                break
            await asyncio.sleep(0.01)
        await manager.reconfigure(DatabaseSettings(password="right"))  # type: ignore[arg-type]
        assert await manager.wait_ready(within_s=5)
        assert manager.settings.password.get_secret_value() == "right"
        with pytest.raises(RuntimeError):
            await manager.reconfigure(DatabaseSettings())
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await manager.dispose()


# ---------------------------------------------------------------- API


async def _client_call(runtime: Runtime, method: str, path: str, **kw: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(runtime))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kw)


async def test_503_names_the_state(tmp_path: Path) -> None:
    runtime = Runtime(load_settings(tmp_path / "none.toml"))
    try:
        response = await _client_call(runtime, "GET", "/api/auth/me")
    finally:
        await runtime.db.dispose()
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "db_unavailable"
    assert body["state"] == diagnosis.CONNECTING
    assert isinstance(body["detail"], str)


async def test_db_status_and_save_connection_validation(tmp_path: Path) -> None:
    runtime = Runtime(load_settings(tmp_path / "none.toml"))
    try:
        status = await _client_call(runtime, "GET", "/api/db/status")
        assert status.status_code == 200
        body = status.json()
        assert body["state"] == diagnosis.CONNECTING
        assert body["can_reconfigure"] is True
        assert body["connection"]["has_password"] is False
        assert "password" not in body["connection"]

        bad = await _client_call(
            runtime,
            "POST",
            "/api/db/test-connection",
            json={"host": "127.0.0.1", "port": 5432, "user": "x", "name": "bad name!"},
        )
        assert bad.status_code == 422

        restore = await _client_call(
            runtime, "POST", "/api/db/restore", json={"file": "x.dump", "confirm": "wrong"}
        )
        assert restore.status_code == 400
    finally:
        await runtime.db.dispose()


# ---------------------------------------------------------------- backups


def test_backup_names() -> None:
    stamp, kind, before = db_backup.parse_name("nestrisltm-20261004-181500-before-0.4.0.dump")
    assert (kind, before) == ("update", "0.4.0")
    assert stamp is not None and stamp.hour == 18
    assert db_backup.parse_name("nestrisltm-20261004-181500-manual.dump")[1:] == ("manual", None)
    assert db_backup.parse_name("random.dump") == (None, "other", None)


def test_parse_alembic_copy() -> None:
    sql = (
        "--\n-- Data for Name: alembic_version\n--\n\n"
        "COPY public.alembic_version (version_num) FROM stdin;\n0010\n\\.\n\n"
    )
    assert db_backup.parse_alembic_copy(sql) == "0010"
    assert db_backup.parse_alembic_copy("nothing here") is None


def test_aside_name_fits_identifier_limit() -> None:
    name = db_backup.aside_name("x" * 63)
    assert len(name) == 63
    assert db_backup.ASIDE_INFIX in name


def test_resolve_backup_rejects_paths_outside(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "none.toml", data_dir=tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "nestrisltm-20261004-181500-manual.dump").write_bytes(b"PGDMP")
    (tmp_path / "secret.dump").write_bytes(b"PGDMP")
    assert db_backup.resolve_backup(settings, "nestrisltm-20261004-181500-manual.dump").is_file()
    for bad in ("../secret.dump", "missing.dump", "nestrisltm-20261004-181500-manual.txt"):
        with pytest.raises(db_backup.BackupError):
            db_backup.resolve_backup(settings, bad)
