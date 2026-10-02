"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from nestris_ltm import __version__
from nestris_ltm.api import routes_diagnostics, routes_health, routes_pages, routes_ws
from nestris_ltm.db.manager import DatabaseUnavailableError

if TYPE_CHECKING:
    from nestris_ltm.runtime import Runtime


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(title="NestrisLTM", version=__version__, lifespan=lifespan)
    app.state.runtime = runtime

    @app.exception_handler(DatabaseUnavailableError)
    async def _db_unavailable(_: Request, exc: DatabaseUnavailableError) -> JSONResponse:
        return JSONResponse({"detail": f"database unavailable: {exc}"}, status_code=503)

    app.include_router(routes_health.router)
    app.include_router(routes_diagnostics.router)
    app.include_router(routes_ws.router)
    app.include_router(routes_pages.router)
    return app
