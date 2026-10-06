"""Scenes (OBS overlays): management, round control, public state, overlay page.

Round control is also available to API tokens with the ``scenes`` scope, so
a Stream Deck button can start the next round with one HTTP request::

    POST /api/scenes/<slug>/rounds     Authorization: Bearer nltm_...
"""

from __future__ import annotations

import re
import secrets
from importlib import resources
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.api.auth import AdminDep, Principal, require_scope
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.core import scene_flow
from nestris_ltm.core.layouts import LAYOUTS, Layout
from nestris_ltm.core.scene_settings import from_client, normalize
from nestris_ltm.db.models import SCENE_MODES, Game, Player, Scene, SceneSlot, Station
from nestris_ltm.services import audit, overlay_layouts, recordings
from nestris_ltm.services.scenes import SceneEngine

router = APIRouter(prefix="/api/scenes", tags=["scenes"])
pages = APIRouter(include_in_schema=False)
ScenesDep = Annotated[Principal, Depends(require_scope("scenes"))]

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _check_layout(value: str) -> str:
    # Built-in id or "custom:<uuid>"; whether the own layout exists is checked
    # against the database in the route (_layout_of).
    if not overlay_layouts.is_known_syntax(value):
        raise ValueError(f"unknown layout, choose one of {sorted(LAYOUTS)} or custom:<id>")
    return value


def _check_settings(value: dict[str, Any] | None) -> dict[str, Any] | None:
    # Strict: unknown keys or invalid values are a 422 (core/scene_settings.py).
    return None if value is None else from_client(value).stored()


def _check_mode(value: str) -> str:
    if value not in SCENE_MODES:
        raise ValueError(f"unknown mode, choose one of {list(SCENE_MODES)}")
    return value


class SlotIn(BaseModel):
    slot: int = Field(ge=0, le=7)
    station_id: str | None = Field(default=None, max_length=64)
    label_override: str | None = Field(default=None, max_length=64)
    name_override: str | None = Field(default=None, max_length=64)


class SceneIn(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    layout: str
    mode: str = "none"
    flow: scene_flow.Flow = scene_flow.DEFAULT_FLOW
    settings: dict[str, Any] = Field(default_factory=dict)
    slots: list[SlotIn] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SLUG_RE.match(value):
            raise ValueError("lowercase letters, digits and dashes only")
        return value

    @field_validator("layout")
    @classmethod
    def _layout(cls, value: str) -> str:
        return _check_layout(value)

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        return _check_mode(value)

    @field_validator("settings")
    @classmethod
    def _settings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _check_settings(value) or {}


class ScenePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    layout: str | None = None
    mode: str | None = None
    flow: scene_flow.Flow | None = None
    settings: dict[str, Any] | None = None
    slots: list[SlotIn] | None = None
    # Optimistic locking: the updated_at the editor loaded; 409 when it changed.
    expected_updated_at: str | None = None

    @field_validator("layout")
    @classmethod
    def _layout(cls, value: str | None) -> str | None:
        return None if value is None else _check_layout(value)

    @field_validator("settings")
    @classmethod
    def _settings(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _check_settings(value)

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str | None) -> str | None:
        return None if value is None else _check_mode(value)


class ReplayIn(BaseModel):
    game_id: int
    speed: float = Field(default=1.0, ge=0.25, le=8.0)
    loop: bool = False


class SlotReset(BaseModel):
    slot: int = Field(ge=0, le=7)


def _engine(request: Request) -> SceneEngine:
    engine: SceneEngine = get_runtime(request).scenes
    return engine


def overlay_dist() -> Path:
    return Path(str(resources.files("nestris_ltm"))) / "web" / "overlay"


async def _layout_of(session: AsyncSession, key: str) -> Layout:
    layout = await overlay_layouts.resolve(session, key)
    if layout is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown layout {key!r}")
    return layout


async def _write_slots(
    session: AsyncSession, scene_id: int, layout: Layout, slots: list[SlotIn]
) -> None:
    max_slots = layout.slots
    stations = {s for s in (x.station_id for x in slots) if s}
    if stations:
        known = set(await session.scalars(select(Station.id).where(Station.id.in_(stations))))
        missing = stations - known
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown stations: {sorted(missing)}"
            )
    await session.execute(delete(SceneSlot).where(SceneSlot.scene_id == scene_id))
    for s in slots:
        if s.slot >= max_slots:
            continue
        session.add(
            SceneSlot(
                scene_id=scene_id,
                slot=s.slot,
                station_id=s.station_id or None,
                label_override=s.label_override or None,
                name_override=s.name_override or None,
            )
        )


async def _scene_out(session: AsyncSession, scene: Scene) -> dict[str, Any]:
    slots = (
        await session.scalars(
            select(SceneSlot).where(SceneSlot.scene_id == scene.id).order_by(SceneSlot.slot)
        )
    ).all()
    out = {**audit.snapshot(scene), "slots": [audit.snapshot(s) for s in slots]}
    out["settings"] = normalize(scene.settings)[0].stored()
    return out


# ---------------------------------------------------------------- management


@router.get("/layouts")
async def layouts(session: SessionDep) -> list[dict[str, Any]]:
    """Built-in layouts and the own ones of the layout builder (``custom: true``)."""
    out = [{**layout.as_dict(), "custom": False} for layout in LAYOUTS.values()]
    known = await overlay_layouts.all_layouts(session)
    for key, layout in known.items():
        if key not in LAYOUTS:
            out.append({**layout.as_dict(), "custom": True})
    return out


@router.get("")
async def list_scenes(request: Request, _: AdminDep, session: SessionDep) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(Scene).order_by(Scene.name))).all()
    engine = _engine(request)
    out = []
    for row in rows:
        data = await _scene_out(session, row)
        runtime = engine.scenes.get(row.slug)
        data["round"] = runtime.round.number if runtime else None
        data["rounds"] = (
            [runtime.group_round(g).number for g in runtime.groups()] if runtime else []
        )
        data["clients"] = runtime.channel.subscriber_count if runtime else 0
        out.append(data)
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_scene(
    body: SceneIn, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        if await session.scalar(select(Scene.id).where(Scene.slug == body.slug)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"slug {body.slug!r} already exists")
        layout = await _layout_of(session, body.layout)
        scene = Scene(
            slug=body.slug,
            name=body.name,
            layout=body.layout,
            mode=body.mode,
            flow=body.flow,
            settings=body.settings,
        )
        session.add(scene)
        await session.flush()
        await _write_slots(session, scene.id, layout, body.slots)
        await audit.record(
            session, actor=p.actor, action="create", entity="scene", entity_id=scene.id,
            after=body.model_dump(),
        )  # fmt: skip
        await session.refresh(scene)
        out = await _scene_out(session, scene)
    await _engine(request).load()
    return out


@router.patch("/{scene_id}")
async def update_scene(
    scene_id: int, body: ScenePatch, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    async with session.begin():
        scene = await session.get(Scene, scene_id)
        if scene is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
        before = await _scene_out(session, scene)
        if body.expected_updated_at is not None and body.expected_updated_at != before.get(
            "updated_at"
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "stale", "message": "the scene was changed in the meantime"},
            )
        layout = await _layout_of(session, body.layout or scene.layout)
        if body.settings is not None:
            # The replay state belongs to the scene, not to the editor.
            replay = (scene.settings or {}).get("replay")
            changes["settings"] = from_client(body.settings, keep_replay=replay).stored()
        for key in ("name", "layout", "mode", "flow", "settings"):
            if changes.get(key) is not None:
                setattr(scene, key, changes[key])
        if body.slots is not None:
            await _write_slots(session, scene.id, layout, body.slots)
        await session.flush()
        await session.refresh(scene)
        after = await _scene_out(session, scene)
        diff = audit.changed_fields(before, after)
        if diff:
            await audit.record(
                session, actor=p.actor, action="update", entity="scene", entity_id=scene_id,
                before={k: before.get(k) for k in diff}, after=diff,
            )  # fmt: skip
    await _engine(request).load()
    return after


class FlowIn(BaseModel):
    """The run controls of the Regie page (no editor lock: they never clash)."""

    flow: scene_flow.Flow | None = None
    mode: str | None = None

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str | None) -> str | None:
        return None if value is None else _check_mode(value)


@router.patch("/{scene_id}/flow")
async def update_flow(
    scene_id: int, body: FlowIn, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        scene = await session.get(Scene, scene_id)
        if scene is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
        before = {"flow": scene.flow, "mode": scene.mode}
        if body.flow is not None:
            scene.flow = body.flow
        if body.mode is not None:
            scene.mode = body.mode
        after = {"flow": scene.flow, "mode": scene.mode}
        if after != before:
            await audit.record(
                session, actor=p.actor, action="update", entity="scene", entity_id=scene_id,
                before=before, after=after,
            )  # fmt: skip
    await _engine(request).load()
    return after


class DuplicateIn(BaseModel):
    slug: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=128)


async def free_slug(session: AsyncSession, wanted: str) -> str:
    """``wanted`` or ``wanted-2``, ``wanted-3`` … (max 64 characters)."""
    base = wanted[:60].rstrip("-") or "scene"
    candidate, n = base, 1
    while await session.scalar(select(Scene.id).where(Scene.slug == candidate)) is not None:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


@router.post("/{scene_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_scene(
    scene_id: int, body: DuplicateIn, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, Any]:
    """A copy with a new URL: layout, settings and station slots."""
    async with session.begin():
        src = await session.get(Scene, scene_id)
        if src is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
        wanted = body.slug.strip().lower() if body.slug else f"{src.slug}-kopie"
        if not _SLUG_RE.match(wanted):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid slug")
        settings, _ = normalize(src.settings)
        settings.replay = None
        copy = Scene(
            slug=await free_slug(session, wanted),
            name=(body.name or f"{src.name} (Kopie)")[:128],
            layout=src.layout,
            mode=src.mode,
            flow=src.flow,
            settings=settings.stored(),
        )
        session.add(copy)
        await session.flush()
        for slot in await session.scalars(select(SceneSlot).where(SceneSlot.scene_id == src.id)):
            session.add(
                SceneSlot(
                    scene_id=copy.id,
                    slot=slot.slot,
                    station_id=slot.station_id,
                    label_override=slot.label_override,
                    name_override=slot.name_override,
                )
            )
        await audit.record(
            session, actor=p.actor, action="create", entity="scene", entity_id=copy.id,
            after={"duplicate_of": src.slug, "slug": copy.slug},
        )  # fmt: skip
        await session.flush()
        await session.refresh(copy)
        out = await _scene_out(session, copy)
    await _engine(request).load()
    return out


@router.delete("/{scene_id}")
async def delete_scene(
    scene_id: int, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, bool]:
    async with session.begin():
        scene = await session.get(Scene, scene_id)
        if scene is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
        await audit.record(
            session, actor=p.actor, action="delete", entity="scene", entity_id=scene_id,
            before={"slug": scene.slug, "name": scene.name},
        )  # fmt: skip
        await session.delete(scene)
    await _engine(request).load()
    return {"ok": True}


# ---------------------------------------------------------------- round control


@router.post("/{slug}/rounds")
async def new_round(
    slug: str, request: Request, p: ScenesDep, group: int | None = None
) -> dict[str, Any]:
    """Start the next round (frozen results are cleared). Stream-Deck friendly.

    ``?group=N`` restarts only one head-to-head pair (``2x1v1``: 0 = slots 1/2,
    1 = slots 3/4); without it every group starts its next round.
    """
    try:
        numbers = await _engine(request).new_round(slug, group)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True, "round": min(numbers.values()), "rounds": numbers, "by": p.actor}


@router.post("/{slug}/reset-slot")
async def reset_slot(slug: str, body: SlotReset, request: Request, _: ScenesDep) -> dict[str, bool]:
    """Let a slot play again in this round (e.g. a wrong or aborted game was bound)."""
    try:
        await _engine(request).reset_slot(slug, body.slot)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found") from exc
    return {"ok": True}


@router.post("/{slug}/replay")
async def start_replay(
    slug: str, body: ReplayIn, request: Request, p: ScenesDep, session: SessionDep
) -> dict[str, Any]:
    """Play a game in a replay scene (the overlay restarts on every call)."""
    async with session.begin():
        scene = await session.scalar(select(Scene).where(Scene.slug == slug))
        if scene is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
        if scene.layout != "replay":
            raise HTTPException(status.HTTP_409_CONFLICT, "scene does not use the replay layout")
        row = (
            await session.execute(
                select(Game, Player.nickname)
                .outerjoin(Player, Player.id == Game.player_id)
                .where(Game.id == body.game_id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
        game, nickname = row
        if await recordings.recording_bytes(session, game.id) is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "game has no recording or live frames")
        replay = {
            "game_id": game.id,
            "speed": body.speed,
            "loop": body.loop,
            "token": secrets.token_hex(6),
            "player": nickname or game.card_name,
            "score": game.score,
            "lines": game.lines,
            "start_level": game.start_level,
            "end_level": game.end_level,
            "started_at": game.started_at.isoformat(),
        }
        scene.settings = {**scene.settings, "replay": replay}
        await audit.record(
            session, actor=p.actor, action="replay", entity="scene", entity_id=scene.id,
            after={"game_id": game.id, "speed": body.speed},
        )  # fmt: skip
    await _engine(request).load()
    return {"ok": True, "replay": replay}


@router.delete("/{slug}/replay")
async def stop_replay(
    slug: str, request: Request, _: ScenesDep, session: SessionDep
) -> dict[str, bool]:
    async with session.begin():
        scene = await session.scalar(select(Scene).where(Scene.slug == slug))
        if scene is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
        scene.settings = {k: v for k, v in scene.settings.items() if k != "replay"}
    await _engine(request).load()
    return {"ok": True}


@router.get("/{slug}/state")
async def scene_state(slug: str, request: Request) -> dict[str, Any]:
    """Public: what the overlay currently shows."""
    try:
        return _engine(request).snapshot(slug)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found") from exc


# ---------------------------------------------------------------- overlay page


@pages.get("/o/{slug}", response_model=None)
async def overlay_page(slug: str) -> FileResponse | HTMLResponse:
    index = overlay_dist() / "index.html"
    if not index.is_file():
        return HTMLResponse(
            "<p style='font:16px sans-serif;color:#fff;background:#000;padding:20px'>"
            "Overlay build missing: run <code>pnpm build</code> in <code>frontend/</code>.</p>",
            status_code=503,
        )
    return FileResponse(index, headers={"Cache-Control": "no-store"})
