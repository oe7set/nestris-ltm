"""Global settings of the scenes (admin): whether the next round starts by itself.

The flow of each scene (phase / quali / rounds) is set per scene
(``PATCH /api/scenes/{id}/flow``); this is the one switch for all scenes
that play rounds.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nestris_ltm.api.auth import CrewDep
from nestris_ltm.api.deps import SessionDep, get_runtime
from nestris_ltm.core import scene_flow
from nestris_ltm.services import app_settings, audit

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ScenesSettingsIn(BaseModel):
    next_round: scene_flow.NextRound


@router.get("/scenes")
async def scenes_settings(_: CrewDep, request: Request) -> dict[str, Any]:
    engine = get_runtime(request).scenes
    return {"next_round": engine.next_round, "seeded": engine.seeded}


@router.put("/scenes")
async def update_scenes_settings(
    body: ScenesSettingsIn, request: Request, p: CrewDep, session: SessionDep
) -> dict[str, Any]:
    engine = get_runtime(request).scenes
    before = engine.next_round
    async with session.begin():
        await app_settings.put(
            session, app_settings.SCENES_NEXT_ROUND, {"next_round": body.next_round}
        )
        if before != body.next_round:
            await audit.record(
                session, actor=p.actor, action="update", entity="settings",
                entity_id="scenes", before={"next_round": before},
                after={"next_round": body.next_round},
            )  # fmt: skip
    await engine.set_next_round(body.next_round)
    return {"next_round": engine.next_round, "seeded": engine.seeded}
