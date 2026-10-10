"""Player management (admin)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.api.auth import AdminDep, CrewDep
from nestris_ltm.api.deps import SessionDep
from nestris_ltm.db.models import EventPlayerFlags, Game, Player, PlayerCard
from nestris_ltm.services import audit, events
from nestris_ltm.services.players import find_by_nickname, normalize_nickname

router = APIRouter(prefix="/api/players", tags=["players"])


class PlayerFields(BaseModel):
    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    birth_date: date | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    street: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=16)
    city: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=4000)


class PlayerIn(PlayerFields):
    nickname: str = Field(min_length=1, max_length=64)

    @field_validator("nickname")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = normalize_nickname(value)
        if not value:
            raise ValueError("nickname must not be blank")
        return value


class PlayerPatch(PlayerFields):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    auto_created: bool | None = None

    @field_validator("nickname")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = normalize_nickname(value)
        if not value:
            raise ValueError("nickname must not be blank")
        return value


class CardOut(BaseModel):
    uid: str
    card_name: str | None
    first_seen_at: datetime
    last_seen_at: datetime


class CardIn(BaseModel):
    uid: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Fa-f]+$")


class FlagsIn(BaseModel):
    hide_everywhere: bool = False
    hide_from_bracket: bool = False


class MergeIn(BaseModel):
    into_id: int


PlayerSort = Literal["nickname", "created", "games", "best", "best_event", "last_played"]


def _out(player: Player, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    data = audit.snapshot(player)
    data.update(extra or {})
    return data


async def _get(session: AsyncSession, player_id: int) -> Player:
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "player not found")
    return player


async def _ensure_unique(session: AsyncSession, nickname: str, own_id: int | None = None) -> None:
    other = await find_by_nickname(session, nickname)
    if other is not None and other.id != own_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"nickname {other.nickname!r} is already taken"
        )


@router.get("")
async def list_players(
    _: CrewDep,
    session: SessionDep,
    q: str = Query("", max_length=64),
    include_deleted: bool = False,
    only_auto_created: bool = False,
    sort: PlayerSort = "nickname",
    dir_: Literal["asc", "desc"] | None = Query(
        None, alias="dir", description="default: names A-Z, numbers and dates high/new first"
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    event = await events.active_event(session)
    games_total = func.count(Game.id).label("games_total")
    best = func.max(Game.score).label("best_score")
    best_event = func.max(Game.score).filter(events.in_window(event)).label("best_score_event")
    last_played = func.max(Game.started_at).label("last_played_at")
    stmt = (
        select(Player, games_total, best, best_event, last_played)
        .outerjoin(Game, Game.player_id == Player.id)
        .group_by(Player.id)
    )
    if not include_deleted:
        stmt = stmt.where(Player.deleted_at.is_(None))
    if only_auto_created:
        stmt = stmt.where(Player.auto_created.is_(True))
    if q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Player.nickname.ilike(pattern),
                Player.first_name.ilike(pattern),
                Player.last_name.ilike(pattern),
                Player.email.ilike(pattern),
            )
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    column: Any = {
        "nickname": func.lower(Player.nickname),
        "created": Player.created_at,
        "games": games_total,
        "best": best,
        "best_event": best_event,
        "last_played": last_played,
    }[sort]
    direction = dir_ or ("asc" if sort == "nickname" else "desc")
    key = (column.asc() if direction == "asc" else column.desc()).nulls_last()
    order = [key, Player.id.asc() if direction == "asc" else Player.id.desc()]
    rows = (await session.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()

    flags: dict[int, EventPlayerFlags] = {}
    if event is not None and rows:
        result = await session.scalars(
            select(EventPlayerFlags).where(
                EventPlayerFlags.event_id == event.id,
                EventPlayerFlags.player_id.in_([r[0].id for r in rows]),
            )
        )
        flags = {f.player_id: f for f in result}

    items = []
    for player, n_games, best_score, best_score_event, last_played_at in rows:
        f = flags.get(player.id)
        items.append(
            _out(
                player,
                {
                    "games_total": n_games,
                    "best_score": best_score,
                    "best_score_event": best_score_event,
                    "last_played_at": last_played_at,
                    "hide_everywhere": bool(f and f.hide_everywhere),
                    "hide_from_bracket": bool(f and f.hide_from_bracket),
                },
            )
        )
    return {
        "items": items,
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "event": {"id": event.id, "name": event.name} if event else None,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_player(body: PlayerIn, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    async with session.begin():
        await _ensure_unique(session, body.nickname)
        player = Player(**body.model_dump())
        session.add(player)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "nickname is already taken") from exc
        await session.refresh(player)
        after = audit.snapshot(player)
        await audit.record(
            session, actor=principal.actor, action="create", entity="player",
            entity_id=player.id, after=after,
        )  # fmt: skip
    return after


@router.get("/{player_id}")
async def get_player(player_id: int, _: CrewDep, session: SessionDep) -> dict[str, Any]:
    player = await _get(session, player_id)
    cards = (
        await session.scalars(
            select(PlayerCard).where(PlayerCard.player_id == player_id).order_by(PlayerCard.uid)
        )
    ).all()
    event = await events.active_event(session)
    flags = (
        await session.get(EventPlayerFlags, (event.id, player_id)) if event is not None else None
    )
    stats = (
        await session.execute(
            select(
                func.count(Game.id),
                func.max(Game.score),
                func.max(Game.score).filter(events.in_window(event)),
                func.count(Game.id).filter(events.in_window(event)),
            ).where(Game.player_id == player_id)
        )
    ).one()
    return _out(
        player,
        {
            "cards": [CardOut.model_validate(c, from_attributes=True).model_dump() for c in cards],
            "games_total": stats[0],
            "best_score": stats[1],
            "best_score_event": stats[2],
            "games_event": stats[3],
            "event": {"id": event.id, "name": event.name} if event else None,
            "hide_everywhere": bool(flags and flags.hide_everywhere),
            "hide_from_bracket": bool(flags and flags.hide_from_bracket),
        },
    )


@router.patch("/{player_id}")
async def update_player(
    player_id: int, body: PlayerPatch, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    async with session.begin():
        player = await _get(session, player_id)
        before = audit.snapshot(player)
        if changes.get("nickname") is not None:
            await _ensure_unique(session, changes["nickname"], own_id=player_id)
        for key, value in changes.items():
            if key == "nickname" and value is None:
                continue
            setattr(player, key, value)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "nickname is already taken") from exc
        await session.refresh(player)
        after = audit.snapshot(player)
        diff = audit.changed_fields(before, after)
        if diff:
            await audit.record(
                session, actor=principal.actor, action="update", entity="player",
                entity_id=player_id, before={k: before.get(k) for k in diff}, after=diff,
            )  # fmt: skip
    return after


@router.delete("/{player_id}")
async def delete_player(player_id: int, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    """Soft delete: the player disappears from lists and views; games stay."""
    async with session.begin():
        player = await _get(session, player_id)
        if player.deleted_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "player is already deleted")
        player.deleted_at = func.now()
        await audit.record(
            session, actor=principal.actor, action="delete", entity="player",
            entity_id=player_id, before={"nickname": player.nickname},
        )  # fmt: skip
    return {"ok": True}


@router.post("/{player_id}/restore")
async def restore_player(
    player_id: int, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        player = await _get(session, player_id)
        if player.deleted_at is None:
            return {"ok": True}
        await _ensure_unique(session, player.nickname, own_id=player_id)
        player.deleted_at = None
        await audit.record(
            session, actor=principal.actor, action="restore", entity="player",
            entity_id=player_id, after={"nickname": player.nickname},
        )  # fmt: skip
    return {"ok": True}


class PlayerBulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: Literal["delete", "restore"]


@router.post("/bulk")
async def bulk_players(
    body: PlayerBulkIn, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """Soft-delete or restore many players.

    Players already in the wanted state, unknown ids and restores whose
    nickname is taken meanwhile are skipped (and reported), the rest is done.
    """
    skipped: list[dict[str, Any]] = []
    affected = 0
    async with session.begin():
        players = {
            p.id: p
            for p in (await session.scalars(select(Player).where(Player.id.in_(body.ids)))).all()
        }
        for player_id in dict.fromkeys(body.ids):
            player = players.get(player_id)
            if player is None:
                skipped.append({"id": player_id, "reason": "not_found"})
                continue
            if body.action == "delete":
                if player.deleted_at is not None:
                    skipped.append({"id": player_id, "reason": "already_deleted"})
                    continue
                player.deleted_at = func.now()
                await audit.record(
                    session, actor=principal.actor, action="delete", entity="player",
                    entity_id=player_id, before={"nickname": player.nickname},
                )  # fmt: skip
            else:
                if player.deleted_at is None:
                    skipped.append({"id": player_id, "reason": "not_deleted"})
                    continue
                other = await find_by_nickname(session, player.nickname)
                if other is not None and other.id != player_id:
                    skipped.append(
                        {"id": player_id, "reason": "nickname_taken", "nickname": player.nickname}
                    )
                    continue
                player.deleted_at = None
                await session.flush()  # the next nickname check must see this one
                await audit.record(
                    session, actor=principal.actor, action="restore", entity="player",
                    entity_id=player_id, after={"nickname": player.nickname},
                )  # fmt: skip
            affected += 1
    return {"action": body.action, "affected": affected, "skipped": skipped}


@router.post("/{player_id}/merge")
async def merge_player(
    player_id: int, body: MergeIn, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """Move games, cards and flags of this player to another one, then delete it.

    For duplicates, e.g. a typo on an RFID card that auto-created a player.
    """
    if body.into_id == player_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "cannot merge into itself")
    async with session.begin():
        source = await _get(session, player_id)
        target = await _get(session, body.into_id)
        if target.deleted_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "target player is deleted")
        moved_games = await session.execute(
            update(Game).where(Game.player_id == player_id).values(player_id=target.id)
        )
        moved_cards = await session.execute(
            update(PlayerCard).where(PlayerCard.player_id == player_id).values(player_id=target.id)
        )
        # Keep the target's own flags; drop the source's.
        await session.execute(
            delete(EventPlayerFlags).where(EventPlayerFlags.player_id == player_id)
        )
        if source.deleted_at is None:
            source.deleted_at = func.now()
        result = {
            "games": moved_games.rowcount,  # type: ignore[attr-defined]
            "cards": moved_cards.rowcount,  # type: ignore[attr-defined]
        }
        await audit.record(
            session, actor=principal.actor, action="merge", entity="player",
            entity_id=player_id,
            before={"nickname": source.nickname},
            after={"into_id": target.id, "into": target.nickname, **result},
        )  # fmt: skip
    return {"ok": True, **result}


# ---------------------------------------------------------------- cards


@router.post("/{player_id}/cards", status_code=status.HTTP_201_CREATED)
async def assign_card(
    player_id: int, body: CardIn, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    uid = body.uid.upper()
    async with session.begin():
        player = await _get(session, player_id)
        previous = await session.scalar(select(PlayerCard.player_id).where(PlayerCard.uid == uid))
        await session.execute(
            insert(PlayerCard)
            .values(uid=uid, player_id=player_id)
            .on_conflict_do_update(index_elements=[PlayerCard.uid], set_={"player_id": player_id})
        )
        await audit.record(
            session, actor=principal.actor, action="assign_card", entity="player",
            entity_id=player_id, before={"uid": uid, "player_id": previous},
            after={"uid": uid, "player_id": player_id, "nickname": player.nickname},
        )  # fmt: skip
    return {"ok": True, "uid": uid}


@router.delete("/{player_id}/cards/{uid}")
async def remove_card(
    player_id: int, uid: str, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        result = await session.execute(
            delete(PlayerCard).where(
                PlayerCard.uid == uid.upper(), PlayerCard.player_id == player_id
            )
        )
        if not result.rowcount:  # type: ignore[attr-defined]
            raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found for this player")
        await audit.record(
            session, actor=principal.actor, action="remove_card", entity="player",
            entity_id=player_id, before={"uid": uid.upper()},
        )  # fmt: skip
    return {"ok": True}


# ---------------------------------------------------------------- visibility per event


@router.put("/{player_id}/flags/{event_id}")
async def set_flags(
    player_id: int, event_id: int, body: FlagsIn, principal: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        await _get(session, player_id)
        await session.execute(
            insert(EventPlayerFlags)
            .values(event_id=event_id, player_id=player_id, **body.model_dump())
            .on_conflict_do_update(
                index_elements=[EventPlayerFlags.event_id, EventPlayerFlags.player_id],
                set_=body.model_dump(),
            )
        )
        await audit.record(
            session, actor=principal.actor, action="flags", entity="player",
            entity_id=player_id, after={"event_id": event_id, **body.model_dump()},
        )  # fmt: skip
    return {"ok": True, **body.model_dump()}
