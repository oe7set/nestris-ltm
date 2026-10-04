"""API for the player terminal (``../nestris-terminal``).

All routes need an API token with the ``terminal`` scope (or an admin). The
terminal's local bridge holds the token; the browser on the touch PC never
sees it. Only nicknames leave this API in lists (highscore); a player's own
page is requested by the terminal while that player's card is on the reader.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import AwareDatetime, BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm import __version__
from nestris_ltm.api.auth import Principal, require_scope
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.db.models import Game, Player, PlayerCard
from nestris_ltm.services import audit, events, highscore, profiles, recordings
from nestris_ltm.services.players import find_by_nickname

router = APIRouter(prefix="/api/terminal/v1", tags=["terminal"])
_terminal_scope = require_scope("terminal")


async def _terminal(request: Request) -> Principal:
    """The terminal scope; also notes the terminal for the device overview
    (it sends its version and reader firmware as headers)."""
    principal: Principal = await _terminal_scope(request)
    if request.headers.get("x-terminal-version"):
        get_runtime(request).devices.note_terminal(
            principal.name,
            request.client.host if request.client else None,
            request.headers.get("x-terminal-version"),
            request.headers.get("x-reader-firmware"),
        )
    return principal


TerminalDep = Annotated[Principal, Depends(_terminal)]

# Names go onto a MIFARE block (16 bytes) and the reader's OLED: plain ASCII.
NICKNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{1,14}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UID_RE = re.compile(r"^[0-9A-Fa-f]{4,32}$")


def _uid(uid: str) -> str:
    if not UID_RE.match(uid):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid card uid")
    return uid.upper()


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


class Registration(BaseModel):
    nickname: str
    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    email_consent: bool = False
    card_uid: str | None = None

    @field_validator("nickname")
    @classmethod
    def _nick(cls, value: str) -> str:
        value = " ".join(value.split())
        if not NICKNAME_RE.match(value):
            raise ValueError("2-15 characters: letters, digits, space . _ -")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        value = _clean(value)
        if value is not None and not EMAIL_RE.match(value):
            raise ValueError("invalid e-mail address")
        return value


class LinkIn(BaseModel):
    player_id: int


class SelfReport(BaseModel):
    score: int = Field(ge=0, le=9_999_999)
    lines: int | None = Field(default=None, ge=0, le=9999)
    start_level: int | None = Field(default=None, ge=0, le=29)
    end_level: int | None = Field(default=None, ge=0, le=255)
    played_at: AwareDatetime | None = None
    note: str | None = Field(default=None, max_length=500)


def _player_summary(player: Player) -> dict[str, Any]:
    return {"id": player.id, "nickname": player.nickname}


async def _player(session: AsyncSession, player_id: int) -> Player:
    player = await session.get(Player, player_id)
    if player is None or player.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "player not found")
    return player


def _live(request: Request) -> dict[str, Any]:
    return highscore.live_values_from_hub(get_runtime(request).hub.stations())


# ---------------------------------------------------------------- status


@router.get("/ping")
async def ping(_: TerminalDep, session: SessionDep) -> dict[str, Any]:
    event = await events.active_event(session)
    return {
        "ok": True,
        "version": __version__,
        "time": datetime.now(UTC).isoformat(),
        "event": {"id": event.id, "name": event.name} if event else None,
    }


# ---------------------------------------------------------------- cards


@router.get("/card/{uid}")
async def card(
    uid: str, _: TerminalDep, session: SessionDep, name: str | None = None
) -> dict[str, Any]:
    """Who owns this card? ``known`` (uid linked), ``name_match`` (the name on
    the card is a nickname; an old card), ``unknown`` (blank or new)."""
    uid = _uid(uid)
    player = await session.scalar(
        select(Player)
        .join(PlayerCard, PlayerCard.player_id == Player.id)
        .where(PlayerCard.uid == uid, Player.deleted_at.is_(None))
    )
    if player is not None:
        return {"status": "known", "uid": uid, "player": _player_summary(player)}
    clean = _clean(name)
    if clean and clean.lower() != "unbekannt":
        match = await find_by_nickname(session, clean)
        if match is not None:
            return {"status": "name_match", "uid": uid, "player": _player_summary(match)}
    return {"status": "unknown", "uid": uid, "name": clean}


@router.post("/card/{uid}/link")
async def link_card(uid: str, body: LinkIn, p: TerminalDep, session: SessionDep) -> dict[str, Any]:
    uid = _uid(uid)
    async with session.begin():
        player = await _player(session, body.player_id)
        await session.execute(
            insert(PlayerCard)
            .values(uid=uid, player_id=player.id, card_name=player.nickname)
            .on_conflict_do_update(
                index_elements=[PlayerCard.uid],
                set_={"player_id": player.id, "last_seen_at": func.now()},
            )
        )
        await audit.record(
            session, actor=p.actor, action="assign_card", entity="player", entity_id=player.id,
            after={"uid": uid},
        )  # fmt: skip
    return {"ok": True, "player": _player_summary(player)}


# ---------------------------------------------------------------- registration


@router.get("/nickname")
async def nickname_available(value: str, _: TerminalDep, session: SessionDep) -> dict[str, Any]:
    clean = " ".join(value.split())
    valid = bool(NICKNAME_RE.match(clean))
    taken = valid and await find_by_nickname(session, clean) is not None
    return {"nickname": clean, "valid": valid, "available": valid and not taken}


@router.post("/players", status_code=status.HTTP_201_CREATED)
async def register(body: Registration, p: TerminalDep, session: SessionDep) -> dict[str, Any]:
    uid = _uid(body.card_uid) if body.card_uid else None
    async with session.begin():
        if await find_by_nickname(session, body.nickname) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "nickname is already taken")
        if uid is not None:
            owner = await session.scalar(
                select(Player.nickname)
                .join(PlayerCard, PlayerCard.player_id == Player.id)
                .where(PlayerCard.uid == uid, Player.deleted_at.is_(None))
            )
            if owner is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "card belongs to another player")
        player = Player(
            nickname=body.nickname,
            first_name=_clean(body.first_name),
            last_name=_clean(body.last_name),
            email=body.email,
            email_consent=body.email_consent and body.email is not None,
            email_consent_at=datetime.now(UTC) if body.email_consent and body.email else None,
        )
        session.add(player)
        await session.flush()
        if uid is not None:
            await session.execute(
                insert(PlayerCard)
                .values(uid=uid, player_id=player.id, card_name=body.nickname)
                .on_conflict_do_update(
                    index_elements=[PlayerCard.uid], set_={"player_id": player.id}
                )
            )
        await audit.record(
            session, actor=p.actor, action="register", entity="player", entity_id=player.id,
            after={"nickname": player.nickname, "card": uid, "email_consent": player.email_consent},
        )  # fmt: skip
    return {"player": _player_summary(player), "card_uid": uid}


# ---------------------------------------------------------------- player page


@router.get("/players/{player_id}")
async def player_profile(
    player_id: int, request: Request, _: TerminalDep, session: SessionDep
) -> dict[str, Any]:
    player = await _player(session, player_id)
    return await profiles.profile(session, player, _live(request))


@router.post("/players/{player_id}/games", status_code=status.HTTP_201_CREATED)
async def self_report(
    player_id: int, body: SelfReport, p: TerminalDep, session: SessionDep
) -> dict[str, Any]:
    """A score the player enters (e.g. the card was forgotten). Counts right
    away; ``source = self_reported`` flags it for the crew."""
    async with session.begin():
        player = await _player(session, player_id)
        played = body.played_at or datetime.now(UTC)
        note = "Am Terminal selbst eingetragen" + (f": {body.note.strip()}" if body.note else "")
        game = Game(
            source="self_reported",
            status="finished",
            player_id=player.id,
            score=body.score,
            lines=body.lines,
            start_level=body.start_level,
            end_level=body.end_level,
            started_at=played,
            ended_at=played,
            notes=note,
        )
        session.add(game)
        await session.flush()
        await audit.record(
            session, actor=p.actor, action="self_report", entity="game", entity_id=game.id,
            after={"player": player.nickname, "score": body.score},
        )  # fmt: skip
    return {"game_id": game.id, "score": body.score}


# ---------------------------------------------------------------- public-ish data


@router.get("/highscore")
async def terminal_highscore(
    request: Request, _: TerminalDep, session: SessionDep, limit: int = 100
) -> dict[str, Any]:
    event = await events.active_event(session)
    standings = await highscore.compute_standings(
        session, event, _live(request), display_count=max(1, min(limit, 1000)), pool_size=0
    )
    return {
        "event": {"id": event.id, "name": event.name} if event else None,
        "stats": standings.stats.model_dump(),
        "entries": [e.model_dump() for e in standings.leaderboard],
    }


@router.get("/games/{game_id}/recording")
async def recording(game_id: int, _: TerminalDep, session: SessionDep) -> Response:
    result = await recordings.recording_bytes(session, game_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no recording for this game")
    data, source = result
    return Response(
        data,
        media_type="application/gzip",
        headers={"X-Recording-Source": source, "Cache-Control": "no-store"},
    )
