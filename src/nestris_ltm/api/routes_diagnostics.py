"""Diagnostics: what is connected and running (admin only)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from nestris_ltm import __version__
from nestris_ltm.api.auth import require_admin_or_local
from nestris_ltm.api.deps import get_runtime
from nestris_ltm.logging_setup import ring_buffer

router = APIRouter(
    prefix="/api/diagnostics", tags=["diagnostics"], dependencies=[Depends(require_admin_or_local)]
)


@router.get("")
async def diagnostics(request: Request) -> dict[str, Any]:
    rt = get_runtime(request)
    db_ok = rt.db.is_ready and await rt.db.ping()
    stats = rt.ingest.stats
    now = datetime.now(UTC)
    return {
        "version": __version__,
        "now": now.isoformat(),
        "uptime_s": int((now - rt.started_at).total_seconds()),
        "database": {
            "ready": db_ok,
            "host": f"{rt.settings.database.host}:{rt.settings.database.port}",
            "name": rt.settings.database.name,
            "ready_since": rt.db.ready_since.isoformat() if rt.db.ready_since else None,
            "error": None if db_ok else rt.db.last_error,
        },
        "mqtt": rt.mqtt.snapshot(),
        "ingest": {
            "messages": stats.messages,
            "parse_errors": stats.parse_errors,
            "last_parse_error": stats.last_parse_error,
            "events_stored": stats.events_stored,
            "events_failed": stats.events_failed,
            "last_event_error": stats.last_event_error,
            "spool_pending": len(rt.spool.pending()),
            "spool_failed": len(rt.spool.failed()),
            "frames_written": rt.frames.frames_written,
            "frames_pending": rt.frames.pending_count,
            "frames_dropped": rt.frames.frames_dropped,
        },
        "websocket_clients": rt.hub.subscriber_count,
        "stations": rt.hub.snapshot(),
    }


@router.get("/logs")
async def logs(
    after_id: int = Query(0, ge=0),
    level: str = Query("INFO"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    buffer = ring_buffer()
    if buffer is None:
        return {"entries": []}
    min_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    entries = buffer.entries(after_id=after_id, min_level=min_level)[-limit:]
    return {
        "entries": [
            {
                "id": e.id,
                "ts": e.ts.isoformat(),
                "level": e.level,
                "logger": e.logger,
                "message": e.message,
            }
            for e in entries
        ]
    }
