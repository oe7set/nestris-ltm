"""Tournament console and kiosk view (ported from TournamentHigscore).

The endpoints mirror the old ``/api/bracket/*``, ``/api/players/*``,
``/api/view/*`` and ``/api/celebration/set`` under ``/api/tournament`` and
now require an admin. Each mutation pushes its result over ``/ws/kiosk``.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from nestris_ltm.api.auth import AdminDep, get_principal
from nestris_ltm.api.deps import get_runtime
from nestris_ltm.core.bracket import MAX_SIZE, MIN_SIZE
from nestris_ltm.services.tournament import NoActiveEventError, TournamentService

router = APIRouter(prefix="/api/tournament", tags=["tournament"])
pages = APIRouter(include_in_schema=False)


def kiosk_dir() -> Path:
    return Path(str(resources.files("nestris_ltm") / "kiosk"))


class ActiveCountIn(BaseModel):
    count: int = Field(ge=MIN_SIZE, le=MAX_SIZE)


class WinnerIn(BaseModel):
    match_id: str = Field(max_length=32)
    user_id: int


class MatchIn(BaseModel):
    match_id: str = Field(max_length=32)


class PlayerIn(BaseModel):
    user_id: int


class ViewSettingsIn(BaseModel):
    font_scale: float | None = Field(default=None, ge=0.6, le=2.5)
    autoscroll: bool | None = None
    effects_enabled: bool | None = None
    banners_enabled: bool | None = None
    box_opacity: float | None = Field(default=None, ge=0.25, le=1.0)


class ScrollIn(BaseModel):
    position: float = Field(ge=0.0, le=1.0)


class CelebrationIn(BaseModel):
    enabled: bool


def _service(request: Request) -> TournamentService:
    service: TournamentService = get_runtime(request).tournament
    return service


async def _mutate(
    request: Request, actor: str, action: str, fn: Any, **details: Any
) -> dict[str, Any]:
    try:
        return await _service(request).mutate(action, actor, fn, **details)
    except NoActiveEventError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


# ---------------------------------------------------------------- read


@router.get("/state")
async def state(request: Request) -> dict[str, Any]:
    """Public snapshot: leaderboard, stats, score train, bracket, view settings."""
    return await _service(request).snapshot()


# ---------------------------------------------------------------- bracket


@router.post("/active-count")
async def set_active_count(body: ActiveCountIn, request: Request, p: AdminDep) -> dict[str, Any]:
    return await _mutate(
        request, p.actor, "size", lambda s: s.set_active_count(body.count), count=body.count
    )


@router.post("/fix")
async def fix(request: Request, p: AdminDep) -> dict[str, Any]:
    return await _mutate(request, p.actor, "fix", lambda s: s.fix())


@router.post("/winner")
async def set_winner(body: WinnerIn, request: Request, p: AdminDep) -> dict[str, Any]:
    return await _mutate(
        request,
        p.actor,
        "winner",
        lambda s: s.set_winner(body.match_id, body.user_id),
        match_id=body.match_id,
        player_id=body.user_id,
    )


@router.post("/clear-winner")
async def clear_winner(body: MatchIn, request: Request, p: AdminDep) -> dict[str, Any]:
    return await _mutate(
        request, p.actor, "clear_winner", lambda s: s.clear_winner(body.match_id),
        match_id=body.match_id,
    )  # fmt: skip


@router.post("/reset")
async def reset(request: Request, p: AdminDep) -> dict[str, Any]:
    return await _mutate(request, p.actor, "reset", lambda s: s.reset())


@router.post("/unseed")
async def unseed(request: Request, p: AdminDep) -> dict[str, Any]:
    return await _mutate(request, p.actor, "unseed", lambda s: s.unseed())


@router.post("/players/disable")
async def disable_player(body: PlayerIn, request: Request, p: AdminDep) -> dict[str, Any]:
    try:
        return await _service(request).set_bracket_excluded(body.user_id, True, p.actor)
    except NoActiveEventError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/players/enable")
async def enable_player(body: PlayerIn, request: Request, p: AdminDep) -> dict[str, Any]:
    try:
        return await _service(request).set_bracket_excluded(body.user_id, False, p.actor)
    except NoActiveEventError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


# ---------------------------------------------------------------- presentation


@router.post("/view/settings")
async def view_settings(body: ViewSettingsIn, request: Request, p: AdminDep) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    return (await _service(request).update_view_settings(changes, p.actor)).model_dump()


@router.post("/view/scroll")
async def view_scroll(body: ScrollIn, request: Request, _: AdminDep) -> dict[str, float]:
    _service(request).scroll_to(body.position)
    return {"position": body.position}


@router.post("/celebration")
async def celebration(body: CelebrationIn, request: Request, p: AdminDep) -> dict[str, bool]:
    return await _service(request).set_celebration(body.enabled, p.actor)


# ---------------------------------------------------------------- pages


@pages.get("/view/highscore")
async def kiosk_view() -> FileResponse:
    """Public highscore + bracket display (options: ?only=highscore|bracket, ?transparent=1)."""
    return FileResponse(kiosk_dir() / "view.html", headers={"Cache-Control": "no-store"})


@pages.get("/view/tournament-admin", response_model=None)
async def tournament_console(request: Request) -> Response:
    """The original tournament console; embedded in the admin UI."""
    principal = await get_principal(request)
    if principal is None or not principal.allows("admin"):
        return RedirectResponse("/#/tournament")
    return FileResponse(kiosk_dir() / "admin.html", headers={"Cache-Control": "no-store"})
