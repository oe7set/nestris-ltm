"""Player lookup for RFID cards.

Resolution order for a card (uid + name written on the card):

1. A known card uid maps to its player (a player may own several cards), so
   the displayed nickname always comes from the database.
2. Otherwise the card name is matched case-insensitively against the
   nicknames; the card uid is then remembered for that player.
3. Otherwise a player with that nickname is auto-created (flagged
   ``auto_created``) and the card is attached to it.
4. A blank card (no name) with an unknown uid, or no card at all, resolves
   to ``None``: the game stays unassigned until the crew assigns it.
"""

from __future__ import annotations

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import Player, PlayerCard

NICKNAME_MAX = 64


def normalize_nickname(name: str) -> str:
    return " ".join(name.split())[:NICKNAME_MAX]


async def find_by_nickname(session: AsyncSession, nickname: str) -> Player | None:
    result = await session.execute(
        select(Player).where(
            func.lower(Player.nickname) == nickname.lower(),
            Player.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def card_nickname(session: AsyncSession, uid: str | None, name: str | None) -> str | None:
    """Display name for a card without creating anything (read-only)."""
    if uid:
        result = await session.execute(
            select(Player.nickname)
            .join(PlayerCard, PlayerCard.player_id == Player.id)
            .where(PlayerCard.uid == uid.strip().upper(), Player.deleted_at.is_(None))
        )
        nickname = result.scalar_one_or_none()
        if nickname is not None:
            return nickname
    if not name:
        return None
    player = await find_by_nickname(session, normalize_nickname(name))
    return player.nickname if player else normalize_nickname(name)


async def resolve_card(session: AsyncSession, uid: str | None, name: str | None) -> int | None:
    """Return the player id for a card, creating player/card links as needed.

    Runs inside the caller's transaction and is safe against concurrent
    calls (all inserts are ``ON CONFLICT DO NOTHING`` followed by a re-read).
    """
    uid = uid.strip().upper() if uid else None
    nickname = normalize_nickname(name) if name else ""

    if uid:
        known = await session.execute(
            select(PlayerCard.player_id)
            .join(Player, Player.id == PlayerCard.player_id)
            .where(PlayerCard.uid == uid, Player.deleted_at.is_(None))
        )
        player_id = known.scalar_one_or_none()
        if player_id is not None:
            await session.execute(
                update(PlayerCard).where(PlayerCard.uid == uid).values(last_seen_at=func.now())
            )
            return player_id

    if not nickname:
        return None

    player = await find_by_nickname(session, nickname)
    if player is None:
        await session.execute(
            insert(Player)
            .values(nickname=nickname, auto_created=True)
            .on_conflict_do_nothing(
                index_elements=[func.lower(Player.nickname)],
                index_where=text("deleted_at IS NULL"),
            )
        )
        player = await find_by_nickname(session, nickname)
        if player is None:  # pragma: no cover - only if deleted concurrently
            return None

    if uid:
        # A uid that belonged to a deleted player is re-pointed to this one.
        await session.execute(
            insert(PlayerCard)
            .values(uid=uid, player_id=player.id, card_name=nickname)
            .on_conflict_do_update(
                index_elements=[PlayerCard.uid],
                set_={"player_id": player.id, "last_seen_at": func.now()},
            )
        )
    return player.id
