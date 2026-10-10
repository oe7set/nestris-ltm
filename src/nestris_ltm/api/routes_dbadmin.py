"""Database problem solving: status, connection settings, backups, restore.

These routes must work while the database is down (that is when they are
needed), so they use ``require_admin_or_local`` (the host itself, or a signed
in admin) and cannot write the audit log until the database is back; they
log through structlog instead. A successful restore is recorded in the audit
log once the database is ready again.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr

from nestris_ltm.api.auth import Principal, require_admin_or_local
from nestris_ltm.api.deps import get_runtime
from nestris_ltm.config import DatabaseSettings, Settings, default_config_path, update_config_file
from nestris_ltm.db import diagnosis
from nestris_ltm.db.bootstrap import app_head, connect_maintenance
from nestris_ltm.services import audit, db_backup
from nestris_ltm.services.db_backup import BackupError
from nestris_ltm.services.updates import find_pg_tool

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/db", tags=["database"])

LocalOrAdmin = Depends(require_admin_or_local)
ENV_PREFIX = "NESTRIS_LTM__DATABASE__"


class ConnectionIn(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    user: str = Field(min_length=1, max_length=63)
    # None keeps the stored password.
    password: str | None = None
    name: str = Field(min_length=1, max_length=63)
    # Save even if the connection test fails (e.g. the server is not up yet).
    force: bool = False


class RestoreIn(BaseModel):
    file: str
    # The database name, typed by the admin as confirmation.
    confirm: str


def _env_overrides() -> list[str]:
    return sorted(k for k in os.environ if k.upper().startswith(ENV_PREFIX))


def _connection(db: DatabaseSettings) -> dict[str, Any]:
    return {
        "host": db.host,
        "port": db.port,
        "user": db.user,
        "name": db.name,
        "has_password": bool(db.password.get_secret_value()),
    }


def _settings_from(body: ConnectionIn, current: DatabaseSettings) -> DatabaseSettings:
    password = current.password if body.password is None else SecretStr(body.password)
    try:
        return current.model_copy(
            update={
                "host": body.host.strip(),
                "port": body.port,
                "user": body.user.strip(),
                "password": password,
                "name": DatabaseSettings.model_validate({"name": body.name.strip()}).name,
            }
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


async def test_connection(db: DatabaseSettings) -> dict[str, Any]:
    """Connect to the server like the bootstrap does; classified result."""
    try:
        conn = await connect_maintenance(db)
    except Exception as exc:
        problem = await diagnosis.diagnose(exc, db)
        return {"ok": False, "state": problem.state, "detail": problem.detail}
    try:
        version = await conn.fetchval("SHOW server_version")
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db.name)
    finally:
        await conn.close()
    return {
        "ok": True,
        "state": diagnosis.READY,
        "detail": f"PostgreSQL {version}",
        "database_exists": bool(exists),
    }


@router.get("/status")
async def db_status(request: Request, _: Principal = LocalOrAdmin) -> dict[str, Any]:
    rt = get_runtime(request)
    db = rt.db
    if db.is_ready:
        await db.ping()
    problem = db.problem
    asides: list[str] = []
    if db.state not in (diagnosis.UNREACHABLE, diagnosis.AUTH_FAILED, diagnosis.AUTH_REJECTED):
        try:
            asides = await db_backup.aside_databases(db.settings)
        except Exception as exc:
            log.debug("cannot list aside databases", error=str(exc))
    return {
        "ready": db.is_ready and problem is None,
        "state": db.state,
        "detail": problem.detail if problem else None,
        "extra": problem.extra if problem else {},
        "attempts": db.attempts,
        "next_retry_at": db.next_retry_at.isoformat() if db.next_retry_at else None,
        "ready_since": db.ready_since.isoformat() if db.ready_since else None,
        "connection": _connection(db.settings),
        "app_head": app_head(),
        "config_file": str(Settings.config_file or default_config_path()),
        "env_overrides": _env_overrides(),
        "aside_databases": asides,
        "can_reconfigure": not db.is_ready,
        "can_restore": not db.is_ready,
    }


@router.post("/retry")
async def retry(request: Request, principal: Principal = LocalOrAdmin) -> dict[str, Any]:
    rt = get_runtime(request)
    rt.db.retry_now()
    log.info("database retry requested", by=principal.actor)
    return {"state": rt.db.state}


@router.post("/test-connection")
async def test(body: ConnectionIn, request: Request, _: Principal = LocalOrAdmin) -> dict[str, Any]:
    rt = get_runtime(request)
    return await test_connection(_settings_from(body, rt.db.settings))


@router.put("/connection")
async def save_connection(
    body: ConnectionIn, request: Request, principal: Principal = LocalOrAdmin
) -> dict[str, Any]:
    rt = get_runtime(request)
    if rt.db.is_ready:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the database is connected; change the connection in config.toml and restart",
        )
    new = _settings_from(body, rt.db.settings)
    result = await test_connection(new)
    if not result["ok"] and not body.force:
        return {"saved": False, "test": result}
    changes: dict[tuple[str, str], object] = {
        ("database", "host"): new.host,
        ("database", "port"): new.port,
        ("database", "user"): new.user,
        ("database", "name"): new.name,
    }
    if body.password is not None:
        changes[("database", "password")] = body.password
    path = Settings.config_file or default_config_path()
    try:
        update_config_file(path, changes)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    # Same object as runtime.settings.database is read by others (updates).
    rt.settings.database = new
    await rt.db.reconfigure(new)
    log.warning(
        "database connection changed",
        by=principal.actor,
        host=new.host,
        port=new.port,
        user=new.user,
        database=new.name,
        password_changed=body.password is not None,
    )
    return {"saved": True, "test": result, "env_overrides": _env_overrides()}


def _backup_error(exc: BackupError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if exc.code == "not_found" else status.HTTP_502_BAD_GATEWAY
    if exc.code in ("no_pg_dump", "no_pg_restore"):
        code = status.HTTP_501_NOT_IMPLEMENTED
    return HTTPException(code, {"code": exc.code, "message": exc.message})


@router.get("/backups")
async def backups(request: Request, _: Principal = LocalOrAdmin) -> dict[str, Any]:
    rt = get_runtime(request)
    items = await db_backup.list_backups(rt.settings)
    return {
        "directory": str(db_backup.backup_dir(rt.settings)),
        "pg_restore": find_pg_tool("pg_restore", rt.settings.updates.pg_dump),
        "items": [b.to_dict() for b in items],
    }


@router.post("/backups")
async def create_backup(request: Request, principal: Principal = LocalOrAdmin) -> dict[str, Any]:
    rt = get_runtime(request)
    try:
        dump = await db_backup.create_manual_backup(rt.settings)
    except BackupError as exc:
        raise _backup_error(exc) from exc
    log.info("manual database backup", by=principal.actor, file=dump.name)
    return {"file": dump.name, "size": dump.stat().st_size}


@router.post("/restore")
async def restore(
    body: RestoreIn, request: Request, principal: Principal = LocalOrAdmin
) -> dict[str, Any]:
    rt = get_runtime(request)
    if rt.db.is_ready:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the database is connected; restore with pg_restore (docs/OPERATIONS.md)",
        )
    if body.confirm.strip() != rt.db.settings.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirmation does not match")
    try:
        dump = db_backup.resolve_backup(rt.settings, body.file)
    except BackupError as exc:
        raise _backup_error(exc) from exc
    log.warning("database restore started", by=principal.actor, backup=dump.name)
    try:
        async with rt.db.maintenance():
            kept_as = await db_backup.restore_backup(rt.settings, dump)
    except BackupError as exc:
        raise _backup_error(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    ready = await rt.db.wait_ready(within_s=60)
    if ready:
        async with rt.db.session() as session, session.begin():
            await audit.record(
                session,
                actor=principal.actor,
                action="restore",
                entity="database",
                entity_id=rt.db.settings.name,
                after={"backup": dump.name, "kept_as": kept_as},
            )
    return {"restored": dump.name, "kept_as": kept_as, "ready": ready, "state": rt.db.state}
