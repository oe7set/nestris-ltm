"""Events (tournament editions), hidden stations, stations and the audit log."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import Select, Text, cast, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.api.auth import AdminDep, CrewDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.db.models import AuditLog, Event, EventHiddenStation, Game, Station
from nestris_ltm.services import audit, events, export

router = APIRouter(prefix="/api", tags=["events"])


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _window(self) -> EventIn:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class EventPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


class StationPatch(BaseModel):
    name: str | None = Field(default=None, max_length=128)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:64] or "event"


async def _get_event(session: AsyncSession, event_id: int) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return event


async def _event_out(session: AsyncSession, event: Event) -> dict[str, Any]:
    stats = (
        await session.execute(
            select(func.count(Game.id), func.count(func.distinct(Game.player_id))).where(
                events.in_window(event)
            )
        )
    ).one()
    hidden = (
        await session.scalars(
            select(EventHiddenStation.station_id).where(EventHiddenStation.event_id == event.id)
        )
    ).all()
    return {
        **audit.snapshot(event),
        "games": stats[0],
        "players": stats[1],
        "hidden_stations": sorted(hidden),
    }


# ---------------------------------------------------------------- events


@router.get("/events")
async def list_events(_: AdminDep, session: SessionDep) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(Event).order_by(Event.starts_at.desc()))).all()
    return [await _event_out(session, e) for e in rows]


@router.get("/events/active")
async def get_active_event(session: SessionDep) -> dict[str, Any] | None:
    """Public: views need the name and window of the running event."""
    event = await events.active_event(session)
    if event is None:
        return None
    return {
        k: v
        for k, v in audit.snapshot(event).items()
        if k in ("id", "name", "slug", "starts_at", "ends_at")
    }


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(body: EventIn, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    async with session.begin():
        slug = body.slug or slugify(body.name)
        if await session.scalar(select(Event.id).where(Event.slug == slug)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"slug {slug!r} already exists")
        event = Event(name=body.name, slug=slug, starts_at=body.starts_at, ends_at=body.ends_at)
        session.add(event)
        await session.flush()
        # The first event becomes active automatically.
        if await session.scalar(select(func.count(Event.id))) == 1:
            await events.activate(session, event.id)
        await session.refresh(event)
        after = audit.snapshot(event)
        await audit.record(
            session, actor=principal.actor, action="create", entity="event", entity_id=event.id,
            after=after,
        )  # fmt: skip
        return await _event_out(session, event)


@router.patch("/events/{event_id}")
async def update_event(
    event_id: int, body: EventPatch, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    async with session.begin():
        event = await _get_event(session, event_id)
        before = audit.snapshot(event)
        for key, value in changes.items():
            if key == "name" and value is None:
                continue
            setattr(event, key, value)
        if event.ends_at is not None and event.ends_at <= event.starts_at:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "ends_at must be after starts_at"
            )
        await session.flush()
        await session.refresh(event)
        after = audit.snapshot(event)
        diff = audit.changed_fields(before, after)
        if diff:
            await audit.record(
                session, actor=principal.actor, action="update", entity="event",
                entity_id=event_id, before={k: before.get(k) for k in diff}, after=diff,
            )  # fmt: skip
        return await _event_out(session, event)


@router.post("/events/{event_id}/activate")
async def activate_event(event_id: int, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    async with session.begin():
        event = await _get_event(session, event_id)
        await events.activate(session, event_id)
        await audit.record(
            session, actor=principal.actor, action="activate", entity="event", entity_id=event_id,
            after={"name": event.name},
        )  # fmt: skip
    return {"ok": True}


@router.delete("/events/{event_id}")
async def delete_event(event_id: int, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    """Deletes the event and its tournament/visibility settings, never games."""
    async with session.begin():
        event = await _get_event(session, event_id)
        if event.is_active:
            raise HTTPException(status.HTTP_409_CONFLICT, "activate another event first")
        before = audit.snapshot(event)
        await session.delete(event)
        await audit.record(
            session, actor=principal.actor, action="delete", entity="event", entity_id=event_id,
            before=before,
        )  # fmt: skip
    return {"ok": True}


@router.put("/events/{event_id}/hidden-stations/{station_id}")
async def hide_station(
    event_id: int, station_id: str, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        await _get_event(session, event_id)
        if await session.get(Station, station_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "station not found")
        await session.execute(
            insert(EventHiddenStation)
            .values(event_id=event_id, station_id=station_id)
            .on_conflict_do_nothing()
        )
        await audit.record(
            session, actor=principal.actor, action="hide", entity="station",
            entity_id=station_id, after={"event_id": event_id},
        )  # fmt: skip
    return {"ok": True}


@router.delete("/events/{event_id}/hidden-stations/{station_id}")
async def unhide_station(
    event_id: int, station_id: str, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        await session.execute(
            delete(EventHiddenStation).where(
                EventHiddenStation.event_id == event_id, EventHiddenStation.station_id == station_id
            )
        )
        await audit.record(
            session, actor=principal.actor, action="unhide", entity="station",
            entity_id=station_id, after={"event_id": event_id},
        )  # fmt: skip
    return {"ok": True}


# ---------------------------------------------------------------- stations


@router.get("/stations")
async def list_stations(request: Request, _: CrewDep, session: SessionDep) -> list[dict[str, Any]]:
    """Stations known to the database, merged with their live state."""
    hub = get_runtime(request).hub
    live = {s["id"]: s for s in hub.snapshot()}
    counts = dict(
        (
            await session.execute(
                select(Game.station_id, func.count(Game.id)).group_by(Game.station_id)
            )
        ).all()
    )
    rows = (await session.scalars(select(Station).order_by(Station.id))).all()
    out = []
    seen = set()
    for st in rows:
        seen.add(st.id)
        out.append({**audit.snapshot(st), "games": counts.get(st.id, 0), "live": live.get(st.id)})
    for sid, snap in live.items():
        if sid not in seen:  # heard on MQTT, not yet synced to the database
            out.append({"id": sid, "name": snap.get("name"), "games": 0, "live": snap})
    return out


@router.get("/stations/{station_id}/metrics")
async def station_metrics(station_id: str, request: Request, _: AdminDep) -> dict[str, Any]:
    """Recent performance of one station (in memory, since the app started)."""
    hub = get_runtime(request).hub
    return {"station": station_id, "points": hub.history(station_id)}


@router.patch("/stations/{station_id}")
async def update_station(
    station_id: str, body: StationPatch, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        station = await session.get(Station, station_id)
        if station is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "station not found")
        before = {"name": station.name}
        station.name = body.name
        await audit.record(
            session, actor=principal.actor, action="update", entity="station",
            entity_id=station_id, before=before, after={"name": body.name},
        )  # fmt: skip
    return {"ok": True}


@router.delete("/stations/{station_id}")
async def delete_station(
    request: Request, station_id: str, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """Forget a station (e.g. a test station). Its games keep their data."""
    state = get_runtime(request).hub.snapshot()
    if any(s["id"] == station_id and s["online"] for s in state):
        raise HTTPException(status.HTTP_409_CONFLICT, "station is online")
    async with session.begin():
        station = await session.get(Station, station_id)
        if station is not None:
            await session.delete(station)
        await audit.record(
            session, actor=principal.actor, action="delete", entity="station",
            entity_id=station_id,
        )  # fmt: skip
    get_runtime(request).hub.forget(station_id)
    return {"ok": True}


# ---------------------------------------------------------------- audit log


def _audit_query(
    entity: str | None,
    entity_id: str | None,
    actor: str | None,
    action: str | None,
    since: AwareDatetime | None,
    until: AwareDatetime | None,
    q: str,
) -> Select[AuditLog]:
    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if since:
        stmt = stmt.where(AuditLog.ts >= since)
    if until:
        stmt = stmt.where(AuditLog.ts <= until)
    if q.strip():
        # Free text over the changed values (JSON as text) and the id.
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                AuditLog.entity_id.ilike(pattern),
                cast(AuditLog.before, Text).ilike(pattern),
                cast(AuditLog.after, Text).ilike(pattern),
            )
        )
    return stmt


@router.get("/audit")
async def list_audit(
    _: AdminDep,
    session: SessionDep,
    entity: str | None = None,
    entity_id: str | None = None,
    actor: str | None = Query(None, max_length=64),
    action: str | None = Query(None, max_length=32),
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    q: str = Query("", max_length=64),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    stmt = _audit_query(entity, entity_id, actor, action, since, until, q)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await session.scalars(
            stmt.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
        )
    ).all()
    return {
        "items": [audit.snapshot(r) for r in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/audit/facets")
async def audit_facets(_: AdminDep, session: SessionDep) -> dict[str, list[str]]:
    """The values that occur, for the filter menus."""

    async def distinct(column: Any) -> list[str]:
        return sorted(str(v) for v in await session.scalars(select(column).distinct()))

    return {
        "entities": await distinct(AuditLog.entity),
        "actions": await distinct(AuditLog.action),
        "actors": await distinct(AuditLog.actor),
    }


@router.get("/audit.csv")
async def audit_csv(
    _: AdminDep,
    session: SessionDep,
    entity: str | None = None,
    entity_id: str | None = None,
    actor: str | None = Query(None, max_length=64),
    action: str | None = Query(None, max_length=32),
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    q: str = Query("", max_length=64),
) -> Response:
    stmt = _audit_query(entity, entity_id, actor, action, since, until, q)
    rows = (await session.scalars(stmt.order_by(AuditLog.ts).limit(100_000))).all()
    data = export.to_csv(
        ("Zeit", "Wer", "Aktion", "Objekt", "ID", "Vorher", "Nachher"),
        (
            (r.ts, r.actor, r.action, r.entity, r.entity_id,
             json.dumps(r.before, ensure_ascii=False) if r.before else "",
             json.dumps(r.after, ensure_ascii=False) if r.after else "")
            for r in rows
        ),
    )  # fmt: skip
    return Response(
        data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nestrisltm-protokoll.csv"'},
    )
