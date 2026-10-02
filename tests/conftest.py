"""Shared fixtures.

Database tests need a PostgreSQL server: set NESTRIS_LTM_TEST_DATABASE_URL to
any database on it (e.g. ``postgresql+asyncpg://postgres:pw@127.0.0.1:5432/postgres``).
Each test session creates and drops its own throwaway databases.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from nestris_ltm.config import DatabaseSettings, Settings

TEST_DB_URL = os.environ.get("NESTRIS_LTM_TEST_DATABASE_URL")


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> Iterator[None]:
    """Never pick up the developer's real config file or env overrides."""
    for key in list(os.environ):
        if key.startswith("NESTRIS_LTM__"):
            monkeypatch.delenv(key)
    Settings.config_file = None
    yield
    Settings.config_file = None


def _server_settings() -> DatabaseSettings:
    if not TEST_DB_URL:
        pytest.skip("NESTRIS_LTM_TEST_DATABASE_URL not set")
    url = make_url(TEST_DB_URL)
    return DatabaseSettings(
        host=url.host or "127.0.0.1",
        port=url.port or 5432,
        user=url.username or "postgres",
        password=url.password or "",  # type: ignore[arg-type]
        name=url.database or "postgres",
    )


async def drop_database(settings: DatabaseSettings) -> None:
    conn = await asyncpg.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password.get_secret_value() or None,
        database="postgres",
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{settings.name}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest.fixture
async def fresh_db_settings() -> AsyncIterator[DatabaseSettings]:
    """Settings for a database name that does not exist yet; dropped afterwards."""
    settings = _server_settings().model_copy(update={"name": f"nltm_test_{uuid.uuid4().hex[:12]}"})
    try:
        yield settings
    finally:
        await drop_database(settings)
