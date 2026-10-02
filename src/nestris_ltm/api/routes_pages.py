"""HTML pages served by the core."""

from __future__ import annotations

from functools import cache
from importlib import resources

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)


@cache
def _page(name: str) -> str:
    return (resources.files("nestris_ltm.api") / "pages" / name).read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
async def status_page() -> HTMLResponse:
    # Interim start page; the admin SPA takes over "/" in phase 4.
    return HTMLResponse(_page("status.html"), headers={"Cache-Control": "no-store"})
