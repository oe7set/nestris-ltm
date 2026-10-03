"""Scenes (OBS overlays): management, round control, public state, overlay page.

Round control is also available to API tokens with the ``scenes`` scope, so
a Stream Deck button can start the next round with one HTTP request::

    POST /api/scenes/<slug>/rounds     Authorization: Bearer nltm_...
"""

from __future__ import annotations

import re
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
from nestris_ltm.core.layouts import LAYOUTS
from nestris_ltm.db.models import SCENE_MODES, Scene, SceneSlot, Station
from nestris_ltm.services import audit
from nestris_ltm.services.scenes import SceneEngine

router = APIRouter(prefix="/api/scenes", tags=["scenes"])
pages = APIRouter(include_in_schema=False)
ScenesDep = Annotated[Principal, Depends(require_scope("scenes"))]

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _check_layout(value: str) -> str:
    if value not in LAYOUTS:
        raise ValueError(f"unknown layout, choose one of {sorted(LAYOUTS)}")
    return value


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
    auto_round: bool = False
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


class ScenePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    layout: str | None = None
    mode: str | None = None
    auto_round: bool | None = None
    settings: dict[str, Any] | None = None
    slots: list[SlotIn] | None = None

    @field_validator("layout")
    @classmethod
    def _layout(cls, value: str | None) -> str | None:
        return None if value is None else _check_layout(value)

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str | None) -> str | None:
        return None if value is None else _check_mode(value)


class SlotReset(BaseModel):
    slot: int = Field(ge=0, le=7)


def _engine(request: Request) -> SceneEngine:
    engine: SceneEngine = get_runtime(request).scenes
    return engine


def overlay_dist() -> Path:
    return Path(str(resources.files("nestris_ltm"))) / "web" / "overlay"


async def _write_slots(
    session: AsyncSession, scene_id: int, layout: str, slots: list[SlotIn]
) -> None:
    max_slots = LAYOUTS[layout].slots
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
    return {**audit.snapshot(scene), "slots": [audit.snapshot(s) for s in slots]}


# ---------------------------------------------------------------- management


@router.get("/layouts")
async def layouts() -> list[dict[str, Any]]:
    return [layout.as_dict() for layout in LAYOUTS.values()]


@router.get("")
async def list_scenes(request: Request, _: AdminDep, session: SessionDep) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(Scene).order_by(Scene.name))).all()
    engine = _engine(request)
    out = []
    for row in rows:
        data = await _scene_out(session, row)
        runtime = engine.scenes.get(row.slug)
        data["round"] = runtime.round.number if runtime else None
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
        scene = Scene(
            slug=body.slug,
            name=body.name,
            layout=body.layout,
            mode=body.mode,
            auto_round=body.auto_round,
            settings=body.settings,
        )
        session.add(scene)
        await session.flush()
        await _write_slots(session, scene.id, body.layout, body.slots)
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
        for key in ("name", "layout", "mode", "auto_round", "settings"):
            if changes.get(key) is not None:
                setattr(scene, key, changes[key])
        if body.slots is not None:
            await _write_slots(session, scene.id, scene.layout, body.slots)
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
async def new_round(slug: str, request: Request, p: ScenesDep) -> dict[str, Any]:
    """Start the next round (frozen results are cleared). Stream-Deck friendly."""
    try:
        number = await _engine(request).new_round(slug)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found") from exc
    return {"ok": True, "round": number, "by": p.actor}


@router.post("/{slug}/reset-slot")
async def reset_slot(slug: str, body: SlotReset, request: Request, _: ScenesDep) -> dict[str, bool]:
    """Let a slot play again in this round (e.g. a wrong or aborted game was bound)."""
    try:
        await _engine(request).reset_slot(slug, body.slot)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found") from exc
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
