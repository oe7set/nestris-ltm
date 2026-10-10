"""Admin changes to games, shared by the single and the bulk routes.

Each function works inside the caller's transaction and writes one audit
entry per game, so a bulk action reads in the audit log exactly like the same
changes made one by one.
"""

from __future__ import annotations

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import EventHiddenGame, Game, Scene
from nestris_ltm.services import audit


async def delete_games(session: AsyncSession, games: list[Game], actor: str) -> bool:
    """Delete games with frames and recordings (DB cascades).

    Replay scenes playing one of them are stopped. Returns True if a scene
    changed (the caller reloads the scene engine after the commit).
    """
    ids = {g.id for g in games}
    for game in games:
        before = audit.snapshot(game)
        await session.delete(game)
        await audit.record(
            session, actor=actor, action="delete", entity="game", entity_id=game.id, before=before
        )
    return await _stop_replays(session, ids)


async def _stop_replays(session: AsyncSession, game_ids: set[int]) -> bool:
    changed = False
    for scene in (await session.scalars(select(Scene).where(Scene.layout == "replay"))).all():
        replay = (scene.settings or {}).get("replay")
        if isinstance(replay, dict) and replay.get("game_id") in game_ids:
            scene.settings = {k: v for k, v in scene.settings.items() if k != "replay"}
            changed = True
    return changed


async def hide_games(
    session: AsyncSession, game_ids: list[int], event_id: int, reason: str | None, actor: str
) -> None:
    for game_id in game_ids:
        await session.execute(
            insert(EventHiddenGame)
            .values(event_id=event_id, game_id=game_id, reason=reason)
            .on_conflict_do_update(
                index_elements=[EventHiddenGame.event_id, EventHiddenGame.game_id],
                set_={"reason": reason},
            )
        )
        await audit.record(
            session, actor=actor, action="hide", entity="game", entity_id=game_id,
            after={"event_id": event_id, "reason": reason},
        )  # fmt: skip


async def unhide_games(
    session: AsyncSession, game_ids: list[int], event_id: int, actor: str
) -> None:
    for game_id in game_ids:
        await session.execute(
            delete(EventHiddenGame).where(
                and_(EventHiddenGame.event_id == event_id, EventHiddenGame.game_id == game_id)
            )
        )
        await audit.record(
            session, actor=actor, action="unhide", entity="game", entity_id=game_id,
            after={"event_id": event_id},
        )  # fmt: skip


async def assign_games(
    session: AsyncSession, games: list[Game], player_id: int | None, actor: str
) -> None:
    """Set (or with None clear) the player of games; marks them as edited."""
    for game in games:
        before = game.player_id
        if before == player_id:
            continue
        game.player_id = player_id
        # A re-delivered station event must not overwrite this.
        game.is_edited = True
        await audit.record(
            session, actor=actor, action="update", entity="game", entity_id=game.id,
            before={"player_id": before}, after={"player_id": player_id},
        )  # fmt: skip
