from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.db.bootstrap import bootstrap
from nestris_ltm.runtime import Runtime


async def _get_health(runtime: Runtime) -> dict[str, object]:
    # ASGITransport does not run the lifespan, so no background tasks start.
    transport = httpx.ASGITransport(app=create_app(runtime))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    return body


async def test_health_degraded_when_database_not_ready(tmp_path: Path) -> None:
    runtime = Runtime(load_settings(tmp_path / "none.toml"))
    try:
        body = await _get_health(runtime)
    finally:
        await runtime.db.dispose()
    assert body["status"] == "degraded"


@pytest.mark.db
async def test_health_ok_with_database(tmp_path: Path, fresh_db_settings: DatabaseSettings) -> None:
    runtime = Runtime(load_settings(tmp_path / "none.toml", database=fresh_db_settings))
    try:
        await bootstrap(fresh_db_settings, runtime.db.engine)
        runtime.db._ready.set()  # what run_bootstrap() does after success
        body = await _get_health(runtime)
    finally:
        await runtime.db.dispose()
    assert body["status"] == "ok"
