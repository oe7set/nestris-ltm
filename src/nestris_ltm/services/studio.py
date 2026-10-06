"""Export and import of scene looks (scene studio).

File format (``*.nltm-scenes.json``)::

    {"format": "nestrisltm/scenes", "version": 1, "app_version": "0.2.0",
     "exported_at": "...",
     "scenes":  [{"slug", "name", "layout", "settings"}],
     "layouts": [{"id", "name", "description", "definition"}]}

Only the look travels: no stations, no player names, no replay state. A
scene's own layout (``custom:<id>``) is exported with it.

Importing is two-step: :func:`analyze` (dry run) reports per entry whether it
is new, identical or in conflict, plus every validation error; :func:`apply`
then carries out the admin's decisions in one transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm import __version__
from nestris_ltm.core import overlay_layout as defs
from nestris_ltm.core.layouts import LAYOUTS
from nestris_ltm.core.scene_settings import from_client, normalize
from nestris_ltm.db.models import OverlayLayout, Scene
from nestris_ltm.services import audit, overlay_layouts

FORMAT = "nestrisltm/scenes"
VERSION = 1
MAX_BYTES = 1024 * 1024
MAX_SCENES = 100
MAX_LAYOUTS = 50

SceneDecision = Literal["create", "rename", "overwrite", "skip"]
LayoutDecision = Literal["create", "keep", "replace", "copy", "skip"]

# What an admin may decide per entry, by the dry run's status.
LAYOUT_ALLOWED: dict[str, set[str]] = {
    "new": {"create", "skip"},
    "same": {"keep", "copy", "skip"},
    "conflict": {"keep", "replace", "copy", "skip"},
}
LAYOUT_DEFAULT: dict[str, LayoutDecision] = {"new": "create", "same": "keep", "conflict": "copy"}
SCENE_ALLOWED: dict[str, set[str]] = {
    "new": {"create", "skip"},
    "conflict": {"rename", "overwrite", "skip"},
}


class ImportError_(ValueError):
    """The file as a whole is unusable (wrong format, too big, broken JSON)."""


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SceneEntry(_Loose):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    layout: str = Field(min_length=1, max_length=64)
    # Files of 0.2.x also carry mode/auto_round/qualifying: ignored (look only).
    settings: dict[str, Any] = Field(default_factory=dict)


class LayoutEntry(_Loose):
    id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    definition: dict[str, Any]


class ExportFile(_Loose):
    format: Literal["nestrisltm/scenes"]
    version: int
    app_version: str | None = None
    exported_at: str | None = None
    scenes: list[SceneEntry] = Field(default_factory=list, max_length=MAX_SCENES)
    layouts: list[LayoutEntry] = Field(default_factory=list, max_length=MAX_LAYOUTS)


# ---------------------------------------------------------------- export


def _scene_look(scene: Scene) -> dict[str, Any]:
    settings, _ = normalize(scene.settings)
    return {
        "slug": scene.slug,
        "name": scene.name,
        "layout": scene.layout,
        "settings": settings.appearance(),
    }


async def export(
    session: AsyncSession, scene_ids: list[int] | None, layout_ids: list[str] | None
) -> dict[str, Any]:
    """Selected scenes (None = all) with their own layouts, plus extra layouts."""
    query = select(Scene).order_by(Scene.name)
    if scene_ids is not None:
        query = query.where(Scene.id.in_(scene_ids))
    scenes = list(await session.scalars(query))
    wanted = {lid for s in scenes if (lid := overlay_layouts.custom_id(s.layout))}
    wanted |= set(layout_ids or [])
    layouts = []
    if wanted:
        for row in await session.scalars(
            select(OverlayLayout).where(OverlayLayout.id.in_(wanted)).order_by(OverlayLayout.name)
        ):
            layouts.append(
                {"id": row.id, "name": row.name, "description": row.description,
                 "definition": row.definition}
            )  # fmt: skip
    return {
        "format": FORMAT,
        "version": VERSION,
        "app_version": __version__,
        "exported_at": datetime.now(UTC).isoformat(),
        "scenes": [_scene_look(s) for s in scenes],
        "layouts": layouts,
    }


# ---------------------------------------------------------------- import


def parse_file(raw: Any, size: int | None = None) -> ExportFile:
    if size is not None and size > MAX_BYTES:
        raise ImportError_(f"file larger than {MAX_BYTES // 1024} KB")
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ImportError_("not a NestrisLTM scene export (format nestrisltm/scenes)")
    if raw.get("version") != VERSION:
        raise ImportError_(f"export version {raw.get('version')!r} is not supported")
    try:
        return ExportFile.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        raise ImportError_(f"{where}: {first['msg']}") from exc


def _scene_errors(entry: SceneEntry, layout_ok: bool) -> list[str]:
    errors = []
    if not entry.slug.replace("-", "").isalnum() or entry.slug != entry.slug.lower():
        errors.append("invalid URL name (lowercase letters, digits, dashes)")
    if not layout_ok:
        errors.append(f"layout {entry.layout!r} is neither built in nor part of the file")
    try:
        from_client(entry.settings)
    except ValidationError as exc:
        errors.extend(
            f"settings: {e['msg']} ({'.'.join(map(str, e['loc']))})" for e in exc.errors()
        )
    return errors


async def _free_slug(session: AsyncSession, wanted: str, taken: set[str]) -> str:
    base = wanted[:60].rstrip("-") or "scene"
    candidate, n = base, 1
    while candidate in taken or (
        await session.scalar(select(Scene.id).where(Scene.slug == candidate)) is not None
    ):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def analyze(session: AsyncSession, file: ExportFile) -> dict[str, Any]:
    """Dry run: what would happen, and what is wrong."""
    layouts_out = []
    file_layouts: set[str] = set()
    for entry in file.layouts:
        item: dict[str, Any] = {"id": entry.id, "name": entry.name, "errors": []}
        try:
            parsed = defs.parse(entry.definition)
        except (ValidationError, ValueError) as exc:
            parsed = None
            item["errors"] = (
                [e["message"] for e in defs.errors(exc)]
                if isinstance(exc, ValidationError)
                else [str(exc)]
            )
        try:
            uuid.UUID(entry.id)
        except ValueError:
            item["errors"].append("invalid layout id")
        existing = await session.get(OverlayLayout, entry.id) if not item["errors"] else None
        if existing is None:
            item["status"] = "new"
        elif parsed is not None and existing.definition == parsed.dump():
            item["status"] = "same"
        else:
            item["status"] = "conflict"
            item["existing_name"] = existing.name
        if not item["errors"]:
            file_layouts.add(entry.id)
        layouts_out.append(item)

    scenes_out = []
    taken: set[str] = set()
    for scene_entry in file.scenes:
        lid = overlay_layouts.custom_id(scene_entry.layout)
        layout_ok = scene_entry.layout in LAYOUTS or (
            lid is not None
            and (lid in file_layouts or await session.get(OverlayLayout, lid) is not None)
        )
        item = {"slug": scene_entry.slug, "name": scene_entry.name, "layout": scene_entry.layout,
                "errors": _scene_errors(scene_entry, layout_ok)}  # fmt: skip
        existing = await session.scalar(select(Scene).where(Scene.slug == scene_entry.slug))
        item["status"] = "conflict" if existing is not None or scene_entry.slug in taken else "new"
        if existing is not None:
            item["existing_name"] = existing.name
        item["suggested_slug"] = await _free_slug(session, scene_entry.slug, taken)
        taken.add(scene_entry.slug)
        scenes_out.append(item)
    ok = not any(i["errors"] for i in scenes_out + layouts_out)
    return {"ok": ok, "scenes": scenes_out, "layouts": layouts_out}


async def apply(
    session: AsyncSession,
    file: ExportFile,
    scene_decisions: dict[str, SceneDecision],
    layout_decisions: dict[str, LayoutDecision],
    actor: str,
) -> dict[str, Any]:
    """Carry out the import inside the caller's transaction (all or nothing)."""
    report = await analyze(session, file)
    if not report["ok"]:
        raise ImportError_("the file has errors; nothing was imported")
    remap: dict[str, str] = {}  # layout id in the file -> id used here
    done: dict[str, list[str]] = {"layouts": [], "scenes": []}
    layout_status = {item["id"]: item["status"] for item in report["layouts"]}
    for entry in file.layouts:
        status = layout_status[entry.id]
        decision = layout_decisions.get(entry.id, LAYOUT_DEFAULT[status])
        if decision not in LAYOUT_ALLOWED[status]:
            raise ImportError_(f"layout {entry.name!r}: {decision!r} is not possible ({status})")
        if decision == "skip":
            continue
        if decision == "create":
            await overlay_layouts.create(
                session, entry.name, entry.description, entry.definition, layout_id=entry.id
            )
            remap[entry.id] = entry.id
        elif decision == "keep":
            remap[entry.id] = entry.id
        elif decision == "replace":
            row = await session.get(OverlayLayout, entry.id)
            assert row is not None
            await overlay_layouts.update(
                session, row, expected_version=row.version, name=entry.name,
                description=entry.description, definition=entry.definition,
            )  # fmt: skip
            remap[entry.id] = entry.id
        else:  # copy: a new layout next to the existing one
            row = await overlay_layouts.create(
                session, f"{entry.name} (Import)"[:64], entry.description, entry.definition
            )
            remap[entry.id] = row.id
        await audit.record(
            session, actor=actor, action="import", entity="layout", entity_id=remap[entry.id],
            after={"name": entry.name, "decision": decision},
        )  # fmt: skip
        done["layouts"].append(entry.name)

    statuses = {item["slug"]: item for item in report["scenes"]}
    taken: set[str] = set()
    for item in file.scenes:
        status_s = statuses[item.slug]["status"]
        decision_s = scene_decisions.get(item.slug, "create" if status_s == "new" else "rename")
        if decision_s not in SCENE_ALLOWED[status_s]:
            raise ImportError_(f"scene {item.slug!r}: {decision_s!r} is not possible ({status_s})")
        if decision_s == "skip":
            continue
        layout = item.layout
        lid = overlay_layouts.custom_id(layout)
        if lid is not None:
            if lid in remap:
                layout = defs.layout_key(remap[lid])
            elif await session.get(OverlayLayout, lid) is None:
                raise ImportError_(f"scene {item.slug!r}: its layout was skipped")
        settings = from_client(item.settings)
        existing = await session.scalar(select(Scene).where(Scene.slug == item.slug))
        if decision_s == "overwrite" and existing is not None:
            keep_replay = (existing.settings or {}).get("replay")
            existing.name = item.name
            existing.layout = layout
            existing.settings = from_client(item.settings, keep_replay=keep_replay).stored()
            await session.flush()
            target_id, slug = existing.id, existing.slug
        else:
            slug = item.slug
            if existing is not None or slug in taken:
                slug = await _free_slug(session, item.slug, taken)
            scene = Scene(slug=slug, name=item.name, layout=layout,
                          settings=settings.stored())  # fmt: skip
            session.add(scene)
            await session.flush()
            target_id = scene.id
        taken.add(slug)
        await audit.record(
            session, actor=actor, action="import", entity="scene", entity_id=target_id,
            after={"slug": slug, "decision": decision_s, "layout": layout},
        )  # fmt: skip
        done["scenes"].append(slug)
    return {"ok": True, "imported": done}
