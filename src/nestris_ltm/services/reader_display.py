"""Text for a station's card reader display (reader protocol v2 ``show``).

When a player places a card at a station, the reader's OLED shows the
nickname and the player's standing in the active event, e.g.
``["Erv", "Platz 3 · 159.867"]``. Lines are at most 21 characters (what the
reader's display takes).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import Player, PlayerCard
from nestris_ltm.services import events, players, profiles

MAX_CHARS = 21


def format_score(value: int) -> str:
    return f"{value:,}".replace(",", ".")


async def card_player(session: AsyncSession, uid: str | None, name: str | None) -> Player | None:
    """The player a card belongs to, without creating anything."""
    if uid:
        player = await session.scalar(
            select(Player)
            .join(PlayerCard, PlayerCard.player_id == Player.id)
            .where(PlayerCard.uid == uid.strip().upper(), Player.deleted_at.is_(None))
        )
        if player is not None:
            return player
    if name:
        return await players.find_by_nickname(session, players.normalize_nickname(name))
    return None


def greeting_lines(nickname: str, standing: dict[str, Any] | None) -> list[str]:
    if standing is not None:
        second = f"Platz {standing['rank']} · {format_score(standing['best_score'])}"
    else:
        second = "Viel Glück!"
    return [nickname[:MAX_CHARS], second[:MAX_CHARS]]


async def card_greeting(
    session: AsyncSession, uid: str | None, name: str | None, live: dict[str, Any]
) -> list[str] | None:
    """Lines for the reader, or ``None`` for an unknown card (the reader's own
    "Neue Karte" screen is right then)."""
    player = await card_player(session, uid, name)
    if player is None:
        return None
    event = await events.active_event(session)
    standing = await profiles.standing_in(session, event, player.id, live) if event else None
    return greeting_lines(player.nickname, standing)
