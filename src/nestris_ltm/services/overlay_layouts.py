"""Own overlay layouts (layout builder) and the lookup "built-in or own".

Scenes name their layout as a string: a built-in id (``core/layouts.py``) or
``custom:<uuid>`` (``overlay_layouts``). Everything that needs slots and
pairs of a scene's layout goes through :func:`resolve` / :func:`all_layouts`.

Saving is optimistic: a write names the ``version`` it started from and
fails with :class:`StaleVersionError` when somebody saved in between.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.core import overlay_layout as defs
from nestris_ltm.core.layouts import LAYOUTS, Layout
from nestris_ltm.db.models import OverlayLayout, Scene


class StaleVersionError(Exception):
    def __init__(self, current: int) -> None:
        super().__init__(f"changed in the meantime (now version {current})")
        self.current = current


class LayoutInUseError(Exception):
    def __init__(self, scenes: list[str]) -> None:
        super().__init__("layout is used by scenes: " + ", ".join(scenes))
        self.scenes = scenes


class InvalidLayoutError(ValueError):
    def __init__(self, exc: ValidationError) -> None:
        super().__init__(str(exc))
        self.errors = defs.errors(exc)


def custom_id(key: str) -> str | None:
    """``custom:<uuid>`` -> ``<uuid>`` (None for built-in ids)."""
    if not key.startswith(defs.CUSTOM_PREFIX):
        return None
    raw = key.removeprefix(defs.CUSTOM_PREFIX)
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return None


def is_known_syntax(key: str) -> bool:
    return key in LAYOUTS or custom_id(key) is not None


def parse_definition(raw: Any) -> defs.LayoutDefinition:
    try:
        return defs.parse(raw)
    except ValidationError as exc:
        raise InvalidLayoutError(exc) from exc


def _layout(row: OverlayLayout) -> Layout | None:
    try:
        definition = defs.parse(row.definition)
    except (ValidationError, ValueError):
        return None  # a broken row never breaks the engine; the builder shows it
    return defs.to_layout(row.id, row.name, row.description, definition)


async def resolve(session: AsyncSession, key: str) -> Layout | None:
    if key in LAYOUTS:
        return LAYOUTS[key]
    lid = custom_id(key)
    if lid is None:
        return None
    row = await session.get(OverlayLayout, lid)
    return _layout(row) if row else None


async def all_layouts(session: AsyncSession) -> dict[str, Layout]:
    """Built-in and own layouts by key."""
    out = dict(LAYOUTS)
    for row in await session.scalars(select(OverlayLayout)):
        layout = _layout(row)
        if layout is not None:
            out[layout.id] = layout
    return out


async def revisions(session: AsyncSession) -> dict[str, str]:
    """``custom:<uuid>`` -> ``<uuid>:<version>`` (overlays reload on change)."""
    rows = await session.execute(select(OverlayLayout.id, OverlayLayout.version))
    return {defs.layout_key(i): f"{i}:{v}" for i, v in rows.all()}


def summary(row: OverlayLayout) -> dict[str, Any]:
    layout = _layout(row)
    return {
        "id": row.id,
        "key": defs.layout_key(row.id),
        "name": row.name,
        "description": row.description,
        "version": row.version,
        "slots": layout.slots if layout else None,
        "pairs": [list(p) for p in layout.pairs] if layout else [],
        "valid": layout is not None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def full(row: OverlayLayout) -> dict[str, Any]:
    return {**summary(row), "definition": row.definition}


async def create(
    session: AsyncSession,
    name: str,
    description: str,
    definition: Any,
    layout_id: str | None = None,
) -> OverlayLayout:
    parsed = parse_definition(definition)
    row = OverlayLayout(
        id=layout_id or str(uuid.uuid4()),
        name=name.strip()[:64] or "Layout",
        description=description.strip()[:500],
        definition=parsed.dump(),
        schema_version=defs.SCHEMA_VERSION,
        version=1,
    )
    session.add(row)
    await session.flush()
    return row


async def update(
    session: AsyncSession,
    row: OverlayLayout,
    *,
    expected_version: int,
    name: str | None = None,
    description: str | None = None,
    definition: Any = None,
) -> OverlayLayout:
    if row.version != expected_version:
        raise StaleVersionError(row.version)
    if definition is not None:
        parsed = parse_definition(definition)
        # Scenes keep working only if their slots still exist.
        users = await using_scenes(session, row.id)
        if users and parsed.slots < (row.definition or {}).get("slots", 0):
            raise ValueError(
                "fewer slots than before while scenes use this layout: " + ", ".join(users)
            )
        row.definition = parsed.dump()
        row.schema_version = defs.SCHEMA_VERSION
    if name is not None:
        row.name = name.strip()[:64] or row.name
    if description is not None:
        row.description = description.strip()[:500]
    row.version += 1
    row.updated_at = func.now()
    await session.flush()
    await session.refresh(row)
    return row


async def using_scenes(session: AsyncSession, layout_id: str) -> list[str]:
    key = defs.layout_key(layout_id)
    return list(await session.scalars(select(Scene.slug).where(Scene.layout == key)))


async def delete(session: AsyncSession, row: OverlayLayout) -> None:
    users = await using_scenes(session, row.id)
    if users:
        raise LayoutInUseError(users)
    await session.delete(row)
