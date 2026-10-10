"""Who is calling: shell, admin session or API token.

- The Qt shell's embedded browser sends ``X-NestrisLTM-Shell-Token`` (a
  random value per run, known only to the local process) -> full admin.
- Admins log in with username/password and get a signed session cookie.
- Machine clients send ``Authorization: Bearer nltm_...`` with scopes.

Public pages (overlays, kiosk) need none of these.
"""

from __future__ import annotations

import hmac
import ipaddress
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from nestris_ltm.db.models import AdminUser
from nestris_ltm.services import auth as auth_service

SESSION_COOKIE = "nltm_session"
# What a helper login may do: event-day work (see CrewDep), scene rounds and
# the remote controls; never deleting or configuring.
HELPER_SCOPES = frozenset({"crew", "scenes", "control"})
SHELL_TOKEN_HEADER = "x-nestrisltm-shell-token"


@dataclass(frozen=True)
class Principal:
    kind: str  # "shell" | "session" | "token"
    name: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    # The admin account of a session.
    user_id: int | None = None
    # Role of a session's account ("admin" | "helper").
    role: str = "admin"

    @property
    def actor(self) -> str:
        """Name written to the audit log."""
        return {"shell": "host", "session": self.name, "token": f"token:{self.name}"}[self.kind]

    def allows(self, scope: str) -> bool:
        if self.kind == "shell" or (self.kind == "session" and self.role == "admin"):
            return True
        return "admin" in self.scopes or scope in self.scopes


def is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "testclient"


async def get_principal(request: Request) -> Principal | None:
    runtime = request.app.state.runtime
    shell = request.headers.get(SHELL_TOKEN_HEADER)
    if shell and hmac.compare_digest(shell, runtime.shell_token):
        return Principal("shell", "host")

    cookie = request.cookies.get(SESSION_COOKIE)
    bearer = request.headers.get("authorization", "")
    if not cookie and not bearer.lower().startswith("bearer "):
        return None

    async with runtime.db.session() as session, session.begin():
        if cookie:
            secret = await auth_service.session_secret(session)
            data = auth_service.parse_session_cookie(secret, cookie)
            if data is not None:
                # A signed cookie alone is not enough: the account must still
                # exist and the cookie must not predate "sign out everywhere"
                # or a password change.
                user = await session.get(AdminUser, data.user_id)
                if user is not None and user.session_version == data.version:
                    scopes = HELPER_SCOPES if user.role == "helper" else frozenset()
                    return Principal(
                        "session", user.username, scopes, user_id=user.id, role=user.role
                    )
        if bearer.lower().startswith("bearer "):
            token = await auth_service.check_api_token(session, bearer[7:].strip())
            if token is not None:
                return Principal("token", token.name, frozenset(token.scopes))
    return None


async def require_admin(request: Request) -> Principal:
    principal = await get_principal(request)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "login required")
    if not principal.allows("admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin scope required")
    return principal


async def require_admin_or_local(request: Request) -> Principal:
    """Admin, or any request from the host itself.

    For diagnostics: they matter most when the database is down, and the
    session/token checks need the database. Loopback callers are on the
    host machine and trusted.
    """
    runtime = request.app.state.runtime
    shell = request.headers.get(SHELL_TOKEN_HEADER)
    if shell and hmac.compare_digest(shell, runtime.shell_token):
        return Principal("shell", "host")
    if is_loopback(request):
        return Principal("shell", "localhost")
    return await require_admin(request)


def require_scope(scope: str):  # type: ignore[no-untyped-def]
    async def dependency(request: Request) -> Principal:
        principal = await get_principal(request)
        if principal is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "login required")
        if not principal.allows(scope):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"scope {scope!r} required")
        return principal

    return dependency


AdminDep = Annotated[Principal, Depends(require_admin)]
# Admins and helpers: looking things up, Regie, hearts, assigning games.
CrewDep = Annotated[Principal, Depends(require_scope("crew"))]


async def require_crew_or_local(request: Request) -> Principal:
    """Like require_admin_or_local, but a helper login is enough (dashboard)."""
    runtime = request.app.state.runtime
    shell = request.headers.get(SHELL_TOKEN_HEADER)
    if shell and hmac.compare_digest(shell, runtime.shell_token):
        return Principal("shell", "host")
    if is_loopback(request):
        return Principal("shell", "localhost")
    principal = await get_principal(request)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "login required")
    if not principal.allows("crew"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "scope 'crew' required")
    return principal


class LoginThrottle:
    """Per client address: at most ``limit`` failures per ``window_s``."""

    def __init__(self, limit: int = 5, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def blocked_for(self, key: str) -> float:
        now = time.monotonic()
        q = self._prune(key, now)
        if len(q) < self.limit:
            return 0.0
        return max(0.0, self.window_s - (now - q[0]))

    def failure(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def success(self, key: str) -> None:
        self._failures.pop(key, None)
