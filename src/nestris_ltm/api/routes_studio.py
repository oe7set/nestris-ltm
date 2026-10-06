"""Scene studio: own overlay layouts (layout builder).

- ``GET /api/overlay-layouts/{id}`` is public: the overlay page loads the
  definition of the layout its scene uses (no secrets in a layout).
- Everything else needs an admin. Saving names the version it started from
  (409 ``stale`` otherwise); invalid definitions answer 422 with the errors
  per element so the builder can mark them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from nestris_ltm.api.auth import AdminDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.db.models import OverlayLayout
from nestris_ltm.services import audit, overlay_layouts
from nestris_ltm.services.overlay_layouts import (
    InvalidLayoutError,
    LayoutInUseError,
    StaleVersionError,
)

router = APIRouter(tags=["studio"])


class LayoutIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    definition: dict[str, Any]


class LayoutUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    definition: dict[str, Any] | None = None


class LayoutCopy(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)


def _invalid(exc: InvalidLayoutError) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        {"code": "invalid", "message": "the layout is not valid", "errors": exc.errors},
    )


async def _row(session: SessionDep, layout_id: str) -> OverlayLayout:
    row = await session.get(OverlayLayout, layout_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "layout not found")
    return row


async def _reload(request: Request) -> None:
    await get_runtime(request).scenes.load()  # scenes pick up the new revision


@router.get("/api/overlay-layouts")
async def list_layouts(_: AdminDep, session: SessionDep) -> list[dict[str, Any]]:
    rows = await session.scalars(select(OverlayLayout).order_by(OverlayLayout.name))
    out = []
    for row in rows:
        item = overlay_layouts.summary(row)
        item["used_by"] = await overlay_layouts.using_scenes(session, row.id)
        out.append(item)
    return out


@router.get("/api/overlay-layouts/{layout_id}")
async def get_layout(layout_id: str, session: SessionDep) -> dict[str, Any]:
    """Public: the overlay renders own layouts from this."""
    return overlay_layouts.full(await _row(session, layout_id))


@router.post("/api/overlay-layouts", status_code=status.HTTP_201_CREATED)
async def create_layout(
    body: LayoutIn, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        try:
            row = await overlay_layouts.create(
                session, body.name, body.description, body.definition
            )
        except InvalidLayoutError as exc:
            raise _invalid(exc) from exc
        await audit.record(
            session, actor=p.actor, action="create", entity="layout", entity_id=row.id,
            after={"name": row.name},
        )  # fmt: skip
        out = overlay_layouts.full(row)
    await _reload(request)
    return out


@router.put("/api/overlay-layouts/{layout_id}")
async def update_layout(
    layout_id: str, body: LayoutUpdate, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        row = await _row(session, layout_id)
        before = {"name": row.name, "version": row.version}
        try:
            row = await overlay_layouts.update(
                session, row, expected_version=body.expected_version, name=body.name,
                description=body.description, definition=body.definition,
            )  # fmt: skip
        except StaleVersionError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "stale", "message": str(exc), "version": exc.current},
            ) from exc
        except InvalidLayoutError as exc:
            raise _invalid(exc) from exc
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, {"code": "in_use", "message": str(exc)}
            ) from exc
        await audit.record(
            session, actor=p.actor, action="update", entity="layout", entity_id=row.id,
            before=before, after={"name": row.name, "version": row.version},
        )  # fmt: skip
        out = overlay_layouts.full(row)
    await _reload(request)
    return out


@router.post("/api/overlay-layouts/{layout_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_layout(
    layout_id: str, body: LayoutCopy, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, Any]:
    async with session.begin():
        src = await _row(session, layout_id)
        try:
            row = await overlay_layouts.create(
                session, body.name or f"{src.name} (Kopie)", src.description, src.definition
            )
        except InvalidLayoutError as exc:
            raise _invalid(exc) from exc
        await audit.record(
            session, actor=p.actor, action="create", entity="layout", entity_id=row.id,
            after={"duplicate_of": src.id, "name": row.name},
        )  # fmt: skip
        out = overlay_layouts.full(row)
    await _reload(request)
    return out


@router.delete("/api/overlay-layouts/{layout_id}")
async def delete_layout(
    layout_id: str, request: Request, p: AdminDep, session: SessionDep
) -> dict[str, bool]:
    async with session.begin():
        row = await _row(session, layout_id)
        try:
            await overlay_layouts.delete(session, row)
        except LayoutInUseError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "in_use", "message": str(exc), "scenes": exc.scenes},
            ) from exc
        await audit.record(
            session, actor=p.actor, action="delete", entity="layout", entity_id=layout_id,
            before={"name": row.name},
        )  # fmt: skip
    await _reload(request)
    return {"ok": True}
