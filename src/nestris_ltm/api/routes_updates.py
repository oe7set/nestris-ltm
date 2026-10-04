"""Update checks and installation (docs/UPDATES.md). Admin only."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from nestris_ltm.api.auth import AdminDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.config import Settings, default_config_path, update_config_file
from nestris_ltm.services import audit
from nestris_ltm.services.updates import UpdateError

router = APIRouter(prefix="/api/updates", tags=["updates"])

# Error codes the admin UI turns into a question rather than an error.
_CONFIRMABLE = {"games_running"}


class InstallIn(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    # "A tournament is running - update anyway?" answered with yes.
    confirm_running: bool = False
    # Install without the pg_dump backup (e.g. pg_dump missing). Explicit only.
    skip_backup: bool = False


class SettingsIn(BaseModel):
    channel: Literal["stable", "beta"] | None = None
    enabled: bool | None = None


@router.put("/settings")
async def update_settings(
    body: SettingsIn, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """Channel (stable/beta) and automatic checks; stored in config.toml."""
    runtime = get_runtime(request)
    cfg = runtime.settings.updates
    changes: dict[tuple[str, str], object] = {}
    if body.channel is not None:
        changes[("updates", "channel")] = body.channel
    if body.enabled is not None:
        changes[("updates", "enabled")] = body.enabled
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nothing to change")
    before = {"channel": cfg.channel, "enabled": cfg.enabled}
    path = Settings.config_file or default_config_path()
    try:
        await asyncio.to_thread(update_config_file, path, changes)
    except (ValueError, OSError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"config not saved: {exc}") from exc
    if body.channel is not None:
        cfg.channel = body.channel
    if body.enabled is not None:
        cfg.enabled = body.enabled
    async with session.begin():
        await audit.record(
            session, actor=principal.name, action="update", entity="settings",
            entity_id="updates", before=before,
            after={"channel": cfg.channel, "enabled": cfg.enabled},
        )  # fmt: skip
    return await runtime.updates.check()


@router.get("")
async def state(request: Request, _: AdminDep) -> dict[str, Any]:
    return get_runtime(request).updates.state()


@router.post("/check")
async def check(request: Request, _: AdminDep) -> dict[str, Any]:
    return await get_runtime(request).updates.check()


@router.get("/releases")
async def releases(request: Request, _: AdminDep) -> list[dict[str, Any]]:
    service = get_runtime(request).updates
    if not service.releases:
        await service.check()
    return service.release_list()


@router.post("/install")
async def install(
    body: InstallIn, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    service = get_runtime(request).updates
    current = str(service.current)
    try:
        result = await service.install(
            body.version, confirm_running=body.confirm_running, skip_backup=body.skip_backup
        )
    except UpdateError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if exc.code in _CONFIRMABLE | {"busy"}
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(code, {"code": exc.code, "message": exc.message}) from exc
    async with session.begin():
        await audit.record(
            session,
            actor=principal.name,
            action="update",
            entity="app",
            entity_id="nestris-ltm",
            before={"version": current},
            after={"version": body.version, "skip_backup": body.skip_backup},
        )
    return result
