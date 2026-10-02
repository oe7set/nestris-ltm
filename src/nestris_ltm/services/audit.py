"""Audit log: who changed what, with before/after snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import AuditLog, Base

# Columns never copied into the audit log.
_SKIP = {"password_hash", "token_hash", "raw_end", "validation", "ngf_gz", "playfield"}


def snapshot(obj: Base) -> dict[str, Any]:
    """JSON-safe column values of an ORM object."""
    out: dict[str, Any] = {}
    for attr in inspect(obj).mapper.column_attrs:
        if attr.key in _SKIP:
            continue
        value = getattr(obj, attr.key)
        if isinstance(value, datetime | date):
            value = value.isoformat()
        elif isinstance(value, bytes):
            continue
        out[attr.key] = value
    return out


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in after.items() if before.get(k) != v and k != "updated_at"}


async def record(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: object,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=actor[:64],
            action=action[:32],
            entity=entity[:32],
            entity_id=str(entity_id)[:64],
            before=before,
            after=after,
        )
    )
