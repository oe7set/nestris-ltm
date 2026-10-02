"""Events (tournament editions) and their time window.

A game belongs to an event when its ``started_at`` lies inside
``[starts_at, ends_at)`` (``ends_at`` NULL = open end). There is no foreign
key, so moving the window re-scopes the data without touching games.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import Event, Game


async def active_event(session: AsyncSession) -> Event | None:
    return await session.scalar(select(Event).where(Event.is_active.is_(True)))


def in_window(event: Event | None) -> ColumnElement[bool]:
    """SQL condition: the game started inside the event window (all games if None)."""
    if event is None:
        return true()
    condition = Game.started_at >= event.starts_at
    if event.ends_at is not None:
        condition = and_(condition, Game.started_at < event.ends_at)
    return condition


async def activate(session: AsyncSession, event_id: int) -> None:
    # Two statements in one transaction: the partial unique index allows
    # only one active event at any point.
    await session.execute(
        update(Event).where(Event.is_active.is_(True), Event.id != event_id).values(is_active=False)
    )
    await session.execute(update(Event).where(Event.id == event_id).values(is_active=True))
