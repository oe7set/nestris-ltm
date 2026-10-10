"""Database problems against a real server: schema too new, wrong password, restore."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from nestris_ltm import __version__
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.db import diagnosis
from nestris_ltm.db.bootstrap import app_head, bootstrap, connect_maintenance
from nestris_ltm.db.diagnosis import SchemaTooNewError
from nestris_ltm.db.manager import DatabaseManager
from nestris_ltm.db.session import create_engine
from nestris_ltm.services import db_backup
from nestris_ltm.services.updates import find_pg_tool, run_pg_dump
from nestris_ltm.setup_cli import _check_db

pytestmark = pytest.mark.db


async def test_upgrade_is_recorded_in_schema_history(fresh_db_settings: DatabaseSettings) -> None:
    engine = create_engine(fresh_db_settings)
    try:
        await bootstrap(fresh_db_settings, engine)
        await bootstrap(fresh_db_settings, engine)  # no-op: no second row
        async with engine.connect() as conn:
            rows = (
                await conn.execute(text("SELECT revision, app_version FROM schema_history"))
            ).all()
    finally:
        await engine.dispose()
    assert rows == [(app_head(), __version__)]


async def test_schema_too_new_leaves_database_untouched(
    fresh_db_settings: DatabaseSettings, tmp_path: Path
) -> None:
    engine = create_engine(fresh_db_settings)
    try:
        await bootstrap(fresh_db_settings, engine)
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE alembic_version SET version_num = 'ffffffff'"))
            await conn.execute(
                text(
                    "INSERT INTO schema_history (revision, app_version) VALUES ('ffffffff', '9.9.9')"
                )
            )
        with pytest.raises(SchemaTooNewError) as info:
            await bootstrap(fresh_db_settings, engine)
        assert info.value.migrated_by == "9.9.9"
        async with engine.connect() as conn:
            assert (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar() == ("ffffffff")
    finally:
        await engine.dispose()

    manager = DatabaseManager(fresh_db_settings)
    task = asyncio.create_task(manager.run_bootstrap(permanent_retry_s=3600))
    try:
        for _ in range(200):
            if manager.problem is not None:
                break
            await asyncio.sleep(0.02)
        assert manager.state == diagnosis.SCHEMA_TOO_NEW
        assert manager.problem is not None
        assert manager.problem.extra["migrated_by"] == "9.9.9"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await manager.dispose()

    check = await _check_db(load_settings(tmp_path / "none.toml", database=fresh_db_settings))
    assert check["ok"] is False
    assert check["state"] == diagnosis.SCHEMA_TOO_NEW


async def test_wrong_password_is_classified(fresh_db_settings: DatabaseSettings) -> None:
    wrong = fresh_db_settings.model_copy(update={"password": SecretStr("definitely-wrong-pw")})
    manager = DatabaseManager(wrong)
    task = asyncio.create_task(manager.run_bootstrap(permanent_retry_s=3600))
    try:
        for _ in range(200):
            if manager.problem is not None:
                break
            await asyncio.sleep(0.02)
        # A server set to "trust" accepts any password; nothing to check then.
        if manager.is_ready:
            pytest.skip("server does not check passwords")
        assert manager.state in (diagnosis.AUTH_FAILED, diagnosis.AUTH_REJECTED)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await manager.dispose()


async def test_restore_roundtrip_keeps_previous_database(
    fresh_db_settings: DatabaseSettings, tmp_path: Path
) -> None:
    if find_pg_tool("pg_restore") is None or find_pg_tool("pg_dump") is None:
        pytest.skip("PostgreSQL client tools not installed")
    settings = load_settings(tmp_path / "none.toml", database=fresh_db_settings, data_dir=tmp_path)
    manager = DatabaseManager(fresh_db_settings)
    aside: str | None = None
    try:
        await manager.run_bootstrap()
        async with manager.session() as session, session.begin():
            await session.execute(text("INSERT INTO players (nickname) VALUES ('Before')"))
        dump = await run_pg_dump(
            settings, db_backup.backup_dir(settings) / "nestrisltm-20261010-120000-manual.dump"
        )
        items = await db_backup.list_backups(settings)
        assert [(b.file, b.revision, b.compatible) for b in items] == [
            (dump.name, app_head(), True)
        ]
        async with manager.session() as session, session.begin():
            await session.execute(text("INSERT INTO players (nickname) VALUES ('After')"))

        manager._ready.clear()  # restores only run while not connected
        async with manager.maintenance():
            aside = await db_backup.restore_backup(settings, dump)
        assert aside is not None
        assert aside in await db_backup.aside_databases(fresh_db_settings)

        manager2 = DatabaseManager(fresh_db_settings)
        try:
            await manager2.run_bootstrap()
            async with manager2.session() as session:
                names = (await session.execute(text("SELECT nickname FROM players"))).scalars()
                assert sorted(names) == ["Before"]
        finally:
            await manager2.dispose()
    finally:
        await manager.dispose()
        if aside:
            conn = await connect_maintenance(fresh_db_settings)
            try:
                await conn.execute(f'DROP DATABASE IF EXISTS "{aside}" WITH (FORCE)')
            finally:
                await conn.close()


async def test_login_probe(fresh_db_settings: DatabaseSettings) -> None:
    from nestris_ltm.db.pgprobe import probe_login

    db = fresh_db_settings
    ok = await probe_login(db.host, db.port, db.user, db.password.get_secret_value())
    assert ok.sqlstate is None
    wrong = await probe_login(db.host, db.port, db.user, "definitely-wrong-pw")
    if wrong.sqlstate is None:
        pytest.skip("server does not check passwords")
    assert wrong.sqlstate == "28P01"
