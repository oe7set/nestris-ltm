"""Devices (stations, terminals, readers) and their updates (docs/UPDATES.md, U4).

- ``/api/devices*``: admin overview and the station update buttons.
- ``GET /api/stations/<station>/updates/<repo>/<tag>/<file>``: the verified
  release cache for the stations (token scope ``stations``, like the
  recording upload).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from nestris_ltm.api.auth import AdminDep, Principal, require_scope
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.services import audit
from nestris_ltm.services.updates import UpdateError

router = APIRouter(tags=["devices"])
StationDep = Annotated[Principal, Depends(require_scope("stations"))]


class StationUpdateIn(BaseModel):
    target: Literal["station", "reader"]
    version: str = Field(min_length=1, max_length=40)
    # Reader only: factory image for readers still on the v1 firmware.
    factory: bool = False


@router.get("/api/devices")
async def devices(request: Request, _: AdminDep) -> dict[str, Any]:
    return get_runtime(request).devices.state()


@router.post("/api/devices/check")
async def check(request: Request, _: AdminDep) -> dict[str, Any]:
    return await get_runtime(request).devices.check()


@router.post("/api/devices/stations/{station_id}/update")
async def update_station(
    station_id: str,
    body: StationUpdateIn,
    request: Request,
    principal: AdminDep,
    session: SessionDep,
) -> dict[str, Any]:
    service = get_runtime(request).devices
    try:
        command = await service.update_station(
            station_id, body.target, body.version, factory=body.factory
        )
    except UpdateError as exc:
        code = {
            "offline": status.HTTP_409_CONFLICT,
            "games_running": status.HTTP_409_CONFLICT,
            "mqtt_offline": status.HTTP_503_SERVICE_UNAVAILABLE,
        }.get(exc.code, status.HTTP_400_BAD_REQUEST)
        raise HTTPException(code, {"code": exc.code, "message": exc.message}) from exc
    async with session.begin():
        await audit.record(
            session,
            actor=principal.name,
            action="update",
            entity="station",
            entity_id=station_id,
            before=None,
            after=command,
        )
    return {"ok": True, "command": command}


@router.get("/api/stations/{station_id}/updates/{repo}/{tag}/{name}")
async def release_file(
    station_id: str, repo: str, tag: str, name: str, request: Request, _: StationDep
) -> FileResponse:
    path = get_runtime(request).devices.cached_file(repo, tag, name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not in the release cache")
    return FileResponse(path, media_type="application/octet-stream", filename=name)
