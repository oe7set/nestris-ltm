"""Remote configuration of the stations (services/station_config.py).

- ``GET  /api/station-config``: template, allowlist, per station: overrides,
  desired set and what the station reports.
- ``PUT  /api/station-config/template``: the template for all stations.
- ``PUT/DELETE /api/stations/<id>/config``: one station's overrides.
- ``POST /api/stations/<id>/config/apply``: send the desired set now.
- ``POST /api/stations/<id>/config/devices``: ask for capture devices.
- ``POST /api/stations/<id>/config/copy``: copy overrides to other stations.
"""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert

from nestris_ltm.api.auth import AdminDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.core import station_config as sc
from nestris_ltm.db.models import Station, StationConfig
from nestris_ltm.services import app_settings, audit
from nestris_ltm.services.station_config import (
    TEMPLATE_KEY,
    StationConfigError,
    get_template,
)

router = APIRouter(tags=["station-config"])

_ERROR_STATUS = {
    "offline": status.HTTP_409_CONFLICT,
    "unsupported": status.HTTP_409_CONFLICT,
    "unmanaged": status.HTTP_409_CONFLICT,
    "mqtt_offline": status.HTTP_503_SERVICE_UNAVAILABLE,
    "db_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
}


class ValuesIn(BaseModel):
    # Nested like the station config file; None leaves remove a key.
    values: dict[str, Any] = Field(default_factory=dict)


class CopyIn(BaseModel):
    targets: list[str] = Field(min_length=1, max_length=64)


def _checked(values: dict[str, Any]) -> dict[str, Any]:
    try:
        return sc.check(sc.prune(values))
    except sc.ConfigError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


def _raise(exc: StationConfigError) -> NoReturn:
    raise HTTPException(
        _ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
        {"code": exc.code, "message": exc.message},
    ) from exc


async def _sync(request: Request, station_id: str) -> bool:
    """Send after an edit; an offline station catches up when it connects."""
    try:
        return await get_runtime(request).station_config.sync(station_id) is not None
    except StationConfigError:
        return False


@router.get("/api/station-config")
async def overview(request: Request, _: AdminDep, session: SessionDep) -> dict[str, Any]:
    return await get_runtime(request).station_config.overview(session)


@router.put("/api/station-config/template")
async def put_template(
    body: ValuesIn, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    values = _checked(body.values)
    async with session.begin():
        before = await get_template(session)
        await app_settings.put(session, TEMPLATE_KEY, {"values": values})
        await audit.record(
            session, actor=principal.actor, action="update", entity="station_config",
            entity_id="template", before=before, after=values,
        )  # fmt: skip
    sent = await get_runtime(request).station_config.sync_all()
    return {"ok": True, "sent": sent}


@router.put("/api/stations/{station_id}/config")
async def put_overrides(
    station_id: str, body: ValuesIn, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    values = _checked(body.values)
    async with session.begin():
        if await session.get(Station, station_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "station not found")
        row = await session.get(StationConfig, station_id)
        before = dict(row.overrides) if row is not None else None
        await session.execute(
            insert(StationConfig)
            .values(station_id=station_id, overrides=values, updated_by=principal.actor[:64])
            .on_conflict_do_update(
                index_elements=[StationConfig.station_id],
                set_={"overrides": values, "updated_by": principal.actor[:64]},
            )
        )
        await audit.record(
            session, actor=principal.actor, action="update", entity="station_config",
            entity_id=station_id, before=before, after=values,
        )  # fmt: skip
    return {"ok": True, "sent": await _sync(request, station_id)}


@router.delete("/api/stations/{station_id}/config")
async def delete_overrides(
    station_id: str, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """Drop the overrides: the station follows the template (if any)."""
    async with session.begin():
        row = await session.get(StationConfig, station_id)
        if row is None:
            return {"ok": True, "sent": False}
        before = dict(row.overrides)
        await session.delete(row)
        await audit.record(
            session, actor=principal.actor, action="delete", entity="station_config",
            entity_id=station_id, before=before,
        )  # fmt: skip
    return {"ok": True, "sent": await _sync(request, station_id)}


@router.post("/api/stations/{station_id}/config/apply")
async def apply(
    station_id: str, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    try:
        command = await get_runtime(request).station_config.sync(station_id, force=True)
    except StationConfigError as exc:
        _raise(exc)
    async with session.begin():
        await audit.record(
            session, actor=principal.actor, action="apply", entity="station_config",
            entity_id=station_id, after=command,
        )  # fmt: skip
    return {"ok": True}


@router.post("/api/stations/{station_id}/config/devices")
async def list_devices(station_id: str, request: Request, _: AdminDep) -> dict[str, Any]:
    try:
        await get_runtime(request).station_config.request(station_id, "list_devices")
    except StationConfigError as exc:
        _raise(exc)
    return {"ok": True}


@router.post("/api/stations/{station_id}/config/copy")
async def copy_overrides(
    station_id: str, body: CopyIn, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """Give other stations the same overrides as this one."""
    async with session.begin():
        row = await session.get(StationConfig, station_id)
        values = dict(row.overrides) if row is not None else {}
        targets = [t for t in dict.fromkeys(body.targets) if t != station_id]
        for target in targets:
            if await session.get(Station, target) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"station {target} not found")
            await session.execute(
                insert(StationConfig)
                .values(station_id=target, overrides=values, updated_by=principal.actor[:64])
                .on_conflict_do_update(
                    index_elements=[StationConfig.station_id],
                    set_={"overrides": values, "updated_by": principal.actor[:64]},
                )
            )
        await audit.record(
            session, actor=principal.actor, action="copy", entity="station_config",
            entity_id=station_id, after={"targets": targets, "values": values},
        )  # fmt: skip
    sent = [t for t in targets if await _sync(request, t)]
    return {"ok": True, "sent": sent}
