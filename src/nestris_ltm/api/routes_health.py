"""Liveness/readiness endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from nestris_ltm import __version__
from nestris_ltm.api.deps import get_runtime

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    runtime = get_runtime(request)
    db_ok = runtime.db.is_ready and await runtime.db.ping()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": {
            "ready": db_ok,
            "name": runtime.settings.database.name,
            "error": None if db_ok else runtime.db.last_error,
        },
    }
