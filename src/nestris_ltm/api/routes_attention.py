"""What needs attention (bell, dashboard) and the failed-event queue."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from nestris_ltm.api.auth import AdminDep, CrewDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.ingest.spool import EventSpool
from nestris_ltm.services import attention, audit

router = APIRouter(prefix="/api", tags=["attention"])

PAYLOAD_PREVIEW = 4000


@router.get("/attention")
async def get_attention(request: Request, _: CrewDep, session: SessionDep) -> dict[str, Any]:
    items = await attention.collect(get_runtime(request), session)
    return {"items": [i.to_dict() for i in items]}


def _describe(spool: EventSpool, name: str) -> dict[str, Any]:
    path = spool.failed_dir / name
    info: dict[str, Any] = {"name": name, "reason": spool.reason(path), "size": path.stat().st_size}
    try:
        event = spool.load(path)
    except (OSError, ValueError, KeyError) as exc:
        info.update(station=None, kind=None, received_at=None, payload=None, unreadable=str(exc))
        return info
    info.update(
        station=event.station,
        kind=event.kind,
        received_at=event.received_at.isoformat(),
        payload=event.payload[:PAYLOAD_PREVIEW],
        truncated=len(event.payload) > PAYLOAD_PREVIEW,
    )
    return info


@router.get("/spool/failed")
async def list_failed(request: Request, _: AdminDep) -> dict[str, Any]:
    spool = get_runtime(request).spool

    def read() -> list[dict[str, Any]]:
        return [_describe(spool, p.name) for p in reversed(spool.failed())]

    return {"items": await asyncio.to_thread(read), "pending": len(spool.pending())}


@router.post("/spool/failed/{name}/retry")
async def retry_failed(
    name: str, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, bool]:
    rt = get_runtime(request)
    if not rt.spool.retry(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "failed event not found")
    rt.ingest.wake()
    async with session.begin():
        await audit.record(
            session, actor=principal.actor, action="retry", entity="spool", entity_id=name
        )
    return {"ok": True}


@router.delete("/spool/failed/{name}")
async def discard_failed(
    name: str, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, bool]:
    spool = get_runtime(request).spool
    path = spool.failed_path(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "failed event not found")
    before = _describe(spool, name)
    before.pop("payload", None)
    spool.discard(name)
    async with session.begin():
        await audit.record(
            session, actor=principal.actor, action="delete", entity="spool", entity_id=name,
            before=before,
        )  # fmt: skip
    return {"ok": True}
