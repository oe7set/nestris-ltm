"""CSV exports, the results of the active event, the backup schedule."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response

from nestris_ltm.api.auth import AdminDep, CrewDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.api.routes_games import games_query
from nestris_ltm.db.models import Game
from nestris_ltm.services import audit, export
from nestris_ltm.services.backup_schedule import ScheduleSettings

router = APIRouter(prefix="/api", tags=["export"])

MAX_GAMES = 100_000


def _csv(data: bytes, name: str) -> Response:
    return Response(
        data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/results")
async def results(request: Request, _: CrewDep, session: SessionDep) -> dict[str, Any]:
    return await export.results(get_runtime(request), session)


@router.get("/export/highscore.csv")
async def highscore_csv(_: AdminDep, session: SessionDep) -> Response:
    data, event = await export.highscore_csv(session)
    return _csv(data, export.filename("highscore", event))


@router.get("/export/players.csv")
async def players_csv(principal: AdminDep, session: SessionDep, contact: bool = False) -> Response:
    if contact:
        # Personal data leaves the system: worth a line in the audit log.
        async with session.begin():
            await audit.record(
                session, actor=principal.actor, action="export", entity="players",
                entity_id="contact",
            )  # fmt: skip
    data = await export.players_csv(session, contact=contact)
    return _csv(data, export.filename("spieler", None))


@router.get("/export/games.csv")
async def games_csv(
    _: AdminDep,
    session: SessionDep,
    event_id: int | None = None,
    all_time: bool = False,
    station_id: str | None = None,
    status_: Literal["live", "finished", "abandoned"] | None = Query(None, alias="status"),
    unassigned: bool = False,
    flagged: bool = False,
    hidden: bool | None = None,
    q: str = Query("", max_length=64),
    min_score: int | None = Query(None, ge=0),
    max_score: int | None = Query(None, ge=0),
) -> Response:
    stmt, event = await games_query(
        session, event_id=event_id, all_time=all_time, station_id=station_id, status_=status_,
        unassigned=unassigned, flagged=flagged, hidden=hidden, q=q,
        min_score=min_score, max_score=max_score,
    )  # fmt: skip
    rows = (await session.execute(stmt.order_by(Game.started_at).limit(MAX_GAMES))).all()
    data = export.to_csv(export.GAME_HEADER, export.game_rows(rows))
    return _csv(data, export.filename("spiele", event))


@router.get("/db/schedule")
async def get_schedule(request: Request, _: AdminDep) -> dict[str, Any]:
    return get_runtime(request).backups.state()


@router.put("/db/schedule")
async def put_schedule(
    body: ScheduleSettings, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    sched = get_runtime(request).backups
    before = sched.settings.model_dump()
    await sched.update(body)
    async with session.begin():
        await audit.record(
            session, actor=principal.actor, action="update", entity="settings",
            entity_id="backup.schedule", before=before, after=body.model_dump(),
        )  # fmt: skip
    return sched.state()


@router.post("/db/schedule/run")
async def run_schedule_now(request: Request, _: AdminDep) -> dict[str, Any]:
    sched = get_runtime(request).backups
    try:
        await sched.run_once()
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, getattr(exc, "message", str(exc))) from exc
    return sched.state()
