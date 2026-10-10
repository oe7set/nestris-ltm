"""Game management (admin): list, inspect, create manually, edit, hide."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.api.auth import AdminDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.db.models import (
    Event,
    EventHiddenGame,
    Game,
    GameCheat,
    GameFrame,
    GameRecording,
    Player,
)
from nestris_ltm.services import audit, events, game_admin

router = APIRouter(prefix="/api/games", tags=["games"])

# Fields the crew may edit; everything else comes from the station.
EDITABLE = (
    "player_id", "score", "lines", "start_level", "end_level", "started_at", "ended_at",
    "station_id", "notes", "status",
)  # fmt: skip


class GameIn(BaseModel):
    player_id: int
    score: int = Field(ge=0, le=9_999_999)
    lines: int | None = Field(default=None, ge=0, le=9999)
    start_level: int | None = Field(default=None, ge=0, le=29)
    end_level: int | None = Field(default=None, ge=0, le=255)
    started_at: AwareDatetime | None = None
    station_id: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=4000)


class GamePatch(BaseModel):
    player_id: int | None = None
    score: int | None = Field(default=None, ge=0, le=9_999_999)
    lines: int | None = Field(default=None, ge=0, le=9999)
    start_level: int | None = Field(default=None, ge=0, le=29)
    end_level: int | None = Field(default=None, ge=0, le=255)
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    station_id: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=4000)
    status: Literal["live", "finished", "abandoned"] | None = None

    @model_validator(mode="after")
    def _window(self) -> GamePatch:
        if self.started_at and self.ended_at and self.ended_at < self.started_at:
            raise ValueError("ended_at must not be before started_at")
        return self


class HideIn(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


def _row(
    game: Game, nickname: str | None, hidden: bool, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = audit.snapshot(game)
    data.update(
        player_nickname=nickname,
        hidden=hidden,
        flagged=bool(game.cheated) or game.valid is False or game.source == "self_reported",
        **(extra or {}),
    )
    return data


async def _event(session: AsyncSession, event_id: int | None) -> Event | None:
    if event_id is None:
        return await events.active_event(session)
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return event


async def _game(session: AsyncSession, game_id: int) -> Game:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    return game


async def _player_exists(session: AsyncSession, player_id: int) -> None:
    if await session.get(Player, player_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "player does not exist")


def _live_values(request: Request) -> dict[str, dict[str, Any]]:
    """Current score/lines/level of running games, keyed by station game id."""
    out: dict[str, dict[str, Any]] = {}
    for station in get_runtime(request).hub.stations():
        live = station.live
        if live is not None and live.game_id:
            out[live.game_id] = {"score": live.score, "lines": live.lines, "level": live.level}
    return out


@router.get("")
async def list_games(
    request: Request,
    _: AdminDep,
    session: SessionDep,
    event_id: int | None = Query(None, description="default: the active event"),
    all_time: bool = Query(False, description="ignore the event window"),
    player_id: int | None = None,
    station_id: str | None = None,
    status_: Literal["live", "finished", "abandoned"] | None = Query(None, alias="status"),
    unassigned: bool = False,
    flagged: bool = Query(False, description="cheat, failed validation or self-reported"),
    hidden: bool | None = Query(None, description="filter by hidden state in the event"),
    q: str = Query("", max_length=64, description="player nickname or card name"),
    sort: Literal["started_at", "score"] = "started_at",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    event = None if all_time else await _event(session, event_id)
    hidden_expr = (
        exists().where(EventHiddenGame.event_id == event.id, EventHiddenGame.game_id == Game.id)
        if event is not None
        else None
    )
    stmt = select(Game, Player.nickname).outerjoin(Player, Player.id == Game.player_id)
    if event is not None:
        stmt = stmt.where(events.in_window(event))
    if player_id is not None:
        stmt = stmt.where(Game.player_id == player_id)
    if station_id:
        stmt = stmt.where(Game.station_id == station_id)
    if status_:
        stmt = stmt.where(Game.status == status_)
    if unassigned:
        stmt = stmt.where(Game.player_id.is_(None))
    if flagged:
        stmt = stmt.where(
            or_(Game.cheated > 0, Game.valid.is_(False), Game.source == "self_reported")
        )
    if hidden is not None and hidden_expr is not None:
        stmt = stmt.where(hidden_expr if hidden else ~hidden_expr)
    if q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Player.nickname.ilike(pattern), Game.card_name.ilike(pattern)))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    order = (
        [Game.score.desc().nulls_last(), Game.started_at.asc()]
        if sort == "score"
        else [Game.started_at.desc()]
    )
    rows = (await session.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()

    hidden_ids: set[int] = set()
    if event is not None and rows:
        hidden_ids = set(
            await session.scalars(
                select(EventHiddenGame.game_id).where(
                    EventHiddenGame.event_id == event.id,
                    EventHiddenGame.game_id.in_([g.id for g, _ in rows]),
                )
            )
        )
    live = _live_values(request)
    return {
        "items": [
            _row(
                g,
                nick,
                g.id in hidden_ids,
                {"live": live.get(g.external_id or "") if g.status == "live" else None},
            )
            for g, nick in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "event": {"id": event.id, "name": event.name} if event else None,
    }


@router.get("/external/{external_id}")
async def game_by_external_id(external_id: str, _: AdminDep, session: SessionDep) -> dict[str, Any]:
    """The game a station reported under its own id (scenes know only that)."""
    row = (
        await session.execute(
            select(Game.id, Game.player_id, Player.nickname)
            .outerjoin(Player, Player.id == Game.player_id)
            .where(Game.external_id == external_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    return {"id": row.id, "player_id": row.player_id, "player_nickname": row.nickname}


@router.get("/{game_id}")
async def get_game(game_id: int, _: AdminDep, session: SessionDep) -> dict[str, Any]:
    game = await _game(session, game_id)
    nickname = (
        await session.scalar(select(Player.nickname).where(Player.id == game.player_id))
        if game.player_id
        else None
    )
    cheats = (
        await session.scalars(
            select(GameCheat).where(GameCheat.game_id == game_id).order_by(GameCheat.ts)
        )
    ).all()
    frame_count = await session.scalar(
        select(func.count()).select_from(GameFrame).where(GameFrame.game_id == game_id)
    )
    recording = await session.get(GameRecording, game_id)
    hidden_in = (
        await session.execute(
            select(Event.id, Event.name, EventHiddenGame.reason)
            .join(EventHiddenGame, EventHiddenGame.event_id == Event.id)
            .where(EventHiddenGame.game_id == game_id)
        )
    ).all()
    event = await events.active_event(session)
    return _row(
        game,
        nickname,
        any(e.id == (event.id if event else None) for e in hidden_in),
        {
            "validation": game.validation,
            "cheats": [audit.snapshot(c) for c in cheats],
            "frame_count": frame_count or 0,
            "recording": (
                {
                    "size_bytes": recording.size_bytes,
                    "received_at": recording.received_at.isoformat(),
                }
                if recording
                else None
            ),
            "hidden_in": [
                {"event_id": e.id, "event": e.name, "reason": e.reason} for e in hidden_in
            ],
        },
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_game(body: GameIn, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    """Enter a result by hand (e.g. a game without a capture station)."""
    async with session.begin():
        await _player_exists(session, body.player_id)
        started = body.started_at or datetime.now(UTC)
        game = Game(
            source="manual",
            status="finished",
            player_id=body.player_id,
            score=body.score,
            lines=body.lines,
            start_level=body.start_level,
            end_level=body.end_level,
            started_at=started,
            ended_at=started,
            station_id=body.station_id or None,
            notes=body.notes,
        )
        session.add(game)
        await session.flush()
        await session.refresh(game)
        after = audit.snapshot(game)
        await audit.record(
            session, actor=principal.actor, action="create", entity="game", entity_id=game.id,
            after=after,
        )  # fmt: skip
    return after


@router.patch("/{game_id}")
async def update_game(
    game_id: int, body: GamePatch, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    unknown = set(changes) - set(EDITABLE)
    if unknown:  # pragma: no cover - the model only has editable fields
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"not editable: {unknown}")
    async with session.begin():
        game = await _game(session, game_id)
        if changes.get("player_id") is not None:
            await _player_exists(session, changes["player_id"])
        before = audit.snapshot(game)
        for key, value in changes.items():
            setattr(game, key, value)
        game.is_edited = True  # a re-delivered station event must not overwrite this
        await session.flush()
        await session.refresh(game)
        after = audit.snapshot(game)
        diff = audit.changed_fields(before, after)
        if diff:
            await audit.record(
                session, actor=principal.actor, action="update", entity="game",
                entity_id=game_id, before={k: before.get(k) for k in diff}, after=diff,
            )  # fmt: skip
    return after


@router.post("/{game_id}/unassign")
async def unassign_game(game_id: int, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    async with session.begin():
        game = await _game(session, game_id)
        await game_admin.assign_games(session, [game], None, principal.actor)
    return {"ok": True}


@router.delete("/{game_id}")
async def delete_game(
    game_id: int, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """Permanently delete a game with its frames and recording. Prefer hiding."""
    async with session.begin():
        game = await _game(session, game_id)
        scenes_changed = await game_admin.delete_games(session, [game], principal.actor)
    if scenes_changed:
        await get_runtime(request).scenes.load()
    return {"ok": True}


@router.put("/{game_id}/hidden/{event_id}")
async def hide_game(
    game_id: int, event_id: int, body: HideIn, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        await _game(session, game_id)
        await _event(session, event_id)
        await game_admin.hide_games(session, [game_id], event_id, body.reason, principal.actor)
    return {"ok": True}


@router.delete("/{game_id}/hidden/{event_id}")
async def unhide_game(
    game_id: int, event_id: int, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        await game_admin.unhide_games(session, [game_id], event_id, principal.actor)
    return {"ok": True}


# ---------------------------------------------------------------- bulk

BULK_MAX = 500


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=BULK_MAX)
    action: Literal["delete", "hide", "unhide", "assign", "unassign"]
    # For "assign".
    player_id: int | None = None
    # For "hide"/"unhide"; default: the active event.
    event_id: int | None = None
    reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _check(self) -> BulkIn:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("ids must not repeat")
        if self.action == "assign" and self.player_id is None:
            raise ValueError("assign needs player_id")
        return self


@router.post("/bulk")
async def bulk_games(
    body: BulkIn, request: Request, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """One action on many games, all or nothing (one audit entry per game)."""
    scenes_changed = False
    async with session.begin():
        games = list((await session.scalars(select(Game).where(Game.id.in_(body.ids)))).all())
        missing = sorted(set(body.ids) - {g.id for g in games})
        if missing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                {"code": "games_not_found", "message": f"games not found: {missing}"},
            )
        actor = principal.actor
        if body.action == "delete":
            scenes_changed = await game_admin.delete_games(session, games, actor)
        elif body.action in ("hide", "unhide"):
            event = await _event(session, body.event_id)
            if event is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {"code": "no_active_event", "message": "no active event to hide games in"},
                )
            if body.action == "hide":
                await game_admin.hide_games(session, body.ids, event.id, body.reason, actor)
            else:
                await game_admin.unhide_games(session, body.ids, event.id, actor)
        elif body.action == "assign":
            assert body.player_id is not None  # checked by the model
            await _player_exists(session, body.player_id)
            await game_admin.assign_games(session, games, body.player_id, actor)
        else:
            await game_admin.assign_games(session, games, None, actor)
    if scenes_changed:
        await get_runtime(request).scenes.load()
    return {"action": body.action, "affected": len(games)}
