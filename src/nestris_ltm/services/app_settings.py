"""Runtime settings edited in the admin UI: the ``settings`` key/value table.

Each key holds a small JSON object. Keys in use:

- ``kiosk.view``, ``kiosk.celebration`` (services/tournament.py)
- ``scenes.next_round`` (``{"next_round": "manual" | "auto"}``, services/scenes.py)
- ``session_secret`` (services/auth.py)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import Setting

SCENES_NEXT_ROUND = "scenes.next_round"


async def get(session: AsyncSession, key: str) -> dict[str, Any] | None:
    row = await session.get(Setting, key)
    return dict(row.value) if row is not None else None


async def put(session: AsyncSession, key: str, value: dict[str, Any]) -> None:
    """Insert or replace (inside the caller's transaction)."""
    await session.execute(
        insert(Setting)
        .values(key=key, value=value)
        .on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
    )
