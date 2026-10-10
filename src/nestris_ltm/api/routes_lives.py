"""Hearts of the 1-vs-1 bracket matches (``services/match_lives.py``).

- ``/api/tournament/matches*``, ``/api/tournament/lives/*``: admin UI.
- ``/api/scenes/{scene_id}/pairs/{pair}/match``: which match a scene pair shows.
- ``/api/control/scenes/{slug}/slots/{slot}/lives/*`` and
  ``/api/control/scenes/{slug}/rounds``: remote controls such as the Stream
  Deck (token scope ``control``). They act on the match bound
  to the slot's pair, so a key keeps one fixed URL ("stage, left player").
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from nestris_ltm.api.auth import AdminDep, CrewDep, Principal, require_scope
from nestris_ltm.api.deps import get_runtime
from nestris_ltm.core import lives as core
from nestris_ltm.services.match_lives import MatchLives
from nestris_ltm.services.tournament import NoActiveEventError

router = APIRouter(tags=["hearts"])
ControlDep = Annotated[Principal, Depends(require_scope("control"))]


class LivesIn(BaseModel):
    player_id: int
    action: Literal["lose", "gain", "set"]
    value: int | None = Field(default=None, ge=0, le=core.MAX_LIVES)


class MaxLivesIn(BaseModel):
    # None = back to the tournament default.
    max_lives: int | None = Field(default=None, ge=1, le=core.MAX_LIVES)


class LivesSettingsIn(BaseModel):
    default_lives: int | None = Field(default=None, ge=1, le=core.MAX_LIVES)
    auto_bind: bool | None = None
    auto_deduct: bool | None = None


class BindIn(BaseModel):
    match_id: str | None = Field(default=None, max_length=16)


def _lives(request: Request) -> MatchLives:
    return get_runtime(request).lives


async def _run(coro: Any) -> Any:
    try:
        return await coro
    except (ValueError, NoActiveEventError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


# ---------------------------------------------------------------- admin


@router.get("/api/tournament/matches")
async def matches(request: Request, _: CrewDep) -> dict[str, Any]:
    return await _lives(request).snapshot()


@router.post("/api/tournament/matches/{match_id}/lives")
async def change(match_id: str, body: LivesIn, request: Request, p: CrewDep) -> dict[str, Any]:
    result: dict[str, Any] = await _run(
        _lives(request).apply(match_id, body.player_id, body.action, body.value, actor=p.actor)
    )
    return result


@router.put("/api/tournament/matches/{match_id}/max-lives")
async def max_lives(
    match_id: str, body: MaxLivesIn, request: Request, p: AdminDep
) -> dict[str, Any]:
    result: dict[str, Any] = await _run(_lives(request).set_max(match_id, body.max_lives, p.actor))
    return result


@router.post("/api/tournament/lives/undo/{event_id}")
async def undo(event_id: int, request: Request, p: CrewDep) -> dict[str, Any]:
    result: dict[str, Any] = await _run(_lives(request).undo(event_id, p.actor))
    return result


@router.put("/api/tournament/lives/settings")
async def settings(body: LivesSettingsIn, request: Request, p: AdminDep) -> dict[str, Any]:
    result: dict[str, Any] = await _run(
        _lives(request).update_settings(body.model_dump(exclude_none=True), p.actor)
    )
    return result


@router.put("/api/scenes/{scene_id}/pairs/{pair}/match")
async def bind(
    scene_id: int, pair: int, body: BindIn, request: Request, p: CrewDep
) -> dict[str, Any]:
    runtime = get_runtime(request)
    scene = next((s for s in runtime.scenes.scenes.values() if s.id == scene_id), None)
    if scene is None or not 0 <= pair < len(scene.layout.pairs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such scene pair")
    await _run(runtime.lives.bind(scene_id, pair, body.match_id, p.actor))
    return {"ok": True, "pair": runtime.lives.pair_info(scene, pair)}


# ---------------------------------------------------------------- Stream Deck & co.


def _target(request: Request, slug: str, slot: int) -> tuple[MatchLives, str, int]:
    runtime = get_runtime(request)
    scene = runtime.scenes.scenes.get(slug)
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no scene {slug!r}")
    try:
        match_id, player_id = runtime.lives.slot_target(scene, slot)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return runtime.lives, match_id, player_id


def _slot_view(service: MatchLives, match_id: str, player_id: int) -> dict[str, Any]:
    view = service.match_view(match_id) or {}
    me: dict[str, Any] = next((p for p in view.get("players", []) if p["id"] == player_id), {})
    return {
        "match_id": match_id,
        "player_id": player_id,
        "player": me.get("nickname"),
        "lives": me.get("lives"),
        "max": view.get("max_lives"),
        "winner_id": view.get("winner_id"),
    }


@router.post("/api/control/scenes/{slug}/rounds")
async def control_new_round(
    slug: str, request: Request, p: ControlDep, group: int | None = None
) -> dict[str, Any]:
    """Next round from the Stream Deck (``?group=N`` = one pair of ``2x1v1``)."""
    try:
        numbers = await get_runtime(request).scenes.new_round(slug, group)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no scene {slug!r}") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True, "rounds": numbers, "by": p.actor}


@router.get("/api/control/scenes/{slug}/slots/{slot}/lives")
async def slot_lives(slug: str, slot: int, request: Request, _: ControlDep) -> dict[str, Any]:
    service, match_id, player_id = _target(request, slug, slot)
    return _slot_view(service, match_id, player_id)


@router.post("/api/control/scenes/{slug}/slots/{slot}/lives/set/{value}")
async def slot_set(
    slug: str, slot: int, value: int, request: Request, p: ControlDep
) -> dict[str, Any]:
    service, match_id, player_id = _target(request, slug, slot)
    await _run(service.apply(match_id, player_id, "set", value, source="api", actor=p.actor))
    return _slot_view(service, match_id, player_id)


@router.post("/api/control/scenes/{slug}/slots/{slot}/lives/{action}")
async def slot_action(
    slug: str,
    slot: int,
    action: Literal["lose", "gain", "cycle", "undo"],
    request: Request,
    p: ControlDep,
) -> dict[str, Any]:
    service, match_id, player_id = _target(request, slug, slot)
    if action == "undo":
        await _run(service.undo_last(match_id, p.actor))
    elif action == "cycle":
        now = _slot_view(service, match_id, player_id)
        target = core.cycle(now["lives"] or 0, now["max"] or service.settings.default_lives)
        await _run(service.apply(match_id, player_id, "set", target, source="api", actor=p.actor))
    else:
        await _run(service.apply(match_id, player_id, action, source="api", actor=p.actor))
    return _slot_view(service, match_id, player_id)
