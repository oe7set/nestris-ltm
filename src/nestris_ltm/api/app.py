"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from nestris_ltm import __version__
from nestris_ltm.api import (
    routes_attention,
    routes_auth,
    routes_dbadmin,
    routes_devices,
    routes_diagnostics,
    routes_events,
    routes_export,
    routes_games,
    routes_health,
    routes_lives,
    routes_pages,
    routes_players,
    routes_recordings,
    routes_scenes,
    routes_settings,
    routes_station_config,
    routes_studio,
    routes_terminal,
    routes_tournament,
    routes_updates,
    routes_ws,
)
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
        # "detail" stays a plain string (clients such as nestris-terminal show
        # it); "code"/"state" let the admin UI switch to its problem screen.
        return JSONResponse(
            {
                "detail": f"database unavailable ({exc.state})",
                "code": "db_unavailable",
                "state": exc.state,
            },
            status_code=503,
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        # Safety net for constraint violations the routes did not pre-check
        # (e.g. a reference to a row deleted concurrently).
        detail = str(exc.orig).splitlines()[0] if exc.orig else "constraint violated"
        return JSONResponse({"detail": f"conflict: {detail}"}, status_code=409)

    for module in (
        routes_health,
        routes_attention,
        routes_auth,
        routes_players,
        routes_recordings,
        routes_games,
        routes_events,
        routes_export,
        routes_tournament,
        routes_scenes,
        routes_settings,
        routes_studio,
        routes_lives,
        routes_terminal,
        routes_updates,
        routes_devices,
        routes_station_config,
        routes_diagnostics,
        routes_dbadmin,
        routes_ws,
        routes_pages,
    ):
        app.include_router(module.router)
    # Hashed bundle files of the admin UI (``pnpm build``); absent in a bare checkout.
    # Kiosk assets ported from TournamentHigscore (JS effects, CSS, fonts, icons).
    app.include_router(routes_tournament.pages)
    app.include_router(routes_scenes.pages)
    # Overlay bundle (frontend/apps/overlay); absent in a bare checkout.
    app.mount(
        "/overlay-assets",
        StaticFiles(directory=routes_scenes.overlay_dist(), check_dir=False),
        name="overlay-assets",
    )
    app.mount(
        "/kiosk/static",
        StaticFiles(directory=routes_tournament.kiosk_dir() / "static"),
        name="kiosk-static",
    )
    app.mount(
        "/assets",
        StaticFiles(directory=routes_pages.admin_dist() / "assets", check_dir=False),
        name="admin-assets",
    )
    return app
