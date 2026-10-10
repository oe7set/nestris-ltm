"""HTML pages: the admin single-page app, the status page, the page registry."""

from __future__ import annotations

import socket
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from nestris_ltm import __version__
from nestris_ltm.api.auth import CrewDep
from nestris_ltm.api.deps import get_runtime
from nestris_ltm.pages import PAGES

router = APIRouter()

NO_STORE = {"Cache-Control": "no-store"}


def admin_dist() -> Path:
    """Build output of frontend/apps/admin (``pnpm build``)."""
    return Path(str(resources.files("nestris_ltm"))) / "web" / "admin"


@cache
def _page(name: str) -> str:
    return (resources.files("nestris_ltm.api") / "pages" / name).read_text(encoding="utf-8")


@router.get("/", include_in_schema=False, response_model=None)
async def index() -> HTMLResponse | FileResponse:
    index_html = admin_dist() / "index.html"
    if index_html.is_file():
        return FileResponse(index_html, headers=NO_STORE)
    # Running from a source checkout without a frontend build.
    return HTMLResponse(_page("status.html"), headers=NO_STORE)


@router.get("/status", include_in_schema=False)
async def status_page() -> HTMLResponse:
    return HTMLResponse(_page("status.html"), headers=NO_STORE)


def _primary_address() -> str | None:
    """The address of the interface used for outgoing traffic (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed for real
            return str(s.getsockname()[0])
    except OSError:
        return None


def _rank(ip: str) -> int:
    """Lower is better: LAN ranges first, link-local (169.254.x) last."""
    if ip.startswith("192.168."):
        return 1
    if ip.startswith("10."):
        return 2
    if ip.startswith("172."):
        return 3  # often Hyper-V/WSL/Docker virtual adapters
    if ip.startswith("169.254."):
        return 9
    return 5


def lan_addresses() -> list[str]:
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    found = {str(i[4][0]) for i in infos} - {""}
    primary = _primary_address()
    if primary:
        found.add(primary)
    found = {ip for ip in found if not ip.startswith("127.")}
    ordered = sorted(found, key=lambda ip: (ip != primary, _rank(ip), ip))
    return ordered


@router.get("/api/meta/pages", tags=["meta"])
async def page_registry(request: Request, _: CrewDep) -> dict[str, Any]:
    port = get_runtime(request).settings.http.port
    return {
        "version": __version__,
        "base_urls": [f"http://127.0.0.1:{port}"]
        + [f"http://{ip}:{port}" for ip in lan_addresses()],
        "pages": [p.as_dict() for p in PAGES],
    }
