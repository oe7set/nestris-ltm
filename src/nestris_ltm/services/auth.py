"""Authentication primitives: admin passwords, session cookies, API tokens.

- Admin passwords are hashed with argon2.
- A session is a signed cookie ``<payload>.<hmac>``; the HMAC secret lives
  in the ``settings`` table, generated on first use, so sessions survive a
  restart and can be revoked all at once by rotating the secret.
- API tokens (machine clients such as the registration kiosk) are random
  strings shown once; only their SHA-256 is stored.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nestris_ltm.db.models import AdminUser, ApiToken, Setting

# "Stay signed in": a persistent cookie, renewed while it is used.
SESSION_TTL_S = 30 * 24 * 3600
# Without it: a browser-session cookie, and the session ends after this anyway.
SHORT_SESSION_TTL_S = 12 * 3600
SESSION_SECRET_KEY = "session_secret"
TOKEN_PREFIX = "nltm_"
# control: remote controls such as the Stream Deck (hearts, rounds).
SCOPES = ("admin", "players:write", "games:write", "stations", "scenes", "terminal", "control")

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------- sessions


@dataclass(frozen=True, slots=True)
class SessionData:
    user_id: int
    username: str
    expires: int
    remember: bool = False
    # AdminUser.session_version when the cookie was issued.
    version: int = 0


async def session_secret(session: AsyncSession) -> bytes:
    """The HMAC key for session cookies, created on first use."""
    value = secrets.token_hex(32)
    await session.execute(
        insert(Setting)
        .values(key=SESSION_SECRET_KEY, value={"value": value})
        .on_conflict_do_nothing(index_elements=[Setting.key])
    )
    stored = await session.scalar(select(Setting.value).where(Setting.key == SESSION_SECRET_KEY))
    assert stored is not None
    return str(stored["value"]).encode("ascii")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def session_ttl(remember: bool) -> int:
    return SESSION_TTL_S if remember else SHORT_SESSION_TTL_S


def make_session_cookie(
    secret: bytes,
    user_id: int,
    username: str,
    now: float | None = None,
    *,
    remember: bool = True,
    version: int = 0,
) -> str:
    expires = int((now or time.time()) + session_ttl(remember))
    payload = {
        "u": user_id, "n": username, "e": expires, "r": 1 if remember else 0, "v": version,
    }  # fmt: skip
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def parse_session_cookie(
    secret: bytes, cookie: str, now: float | None = None
) -> SessionData | None:
    body, _, sig = cookie.partition(".")
    if not body or not sig:
        return None
    expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload: dict[str, Any] = json.loads(_unb64(body))
        data = SessionData(
            int(payload["u"]),
            str(payload["n"]),
            int(payload["e"]),
            # Cookies from before "stay signed in" existed were persistent.
            bool(payload.get("r", 1)),
            int(payload.get("v", 0)),
        )
    except (ValueError, KeyError, TypeError):
        return None
    if data.expires < (now or time.time()):
        return None
    return data


# ---------------------------------------------------------------- admin users


async def admin_count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(AdminUser.id))) or 0)


async def authenticate(session: AsyncSession, username: str, password: str) -> AdminUser | None:
    user = await session.scalar(
        select(AdminUser).where(func.lower(AdminUser.username) == username.strip().lower())
    )
    if user is None:
        # Spend the same time as a real check so usernames cannot be probed.
        verify_password(_DUMMY_HASH, password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = func.now()
    return user


_DUMMY_HASH = hash_password(secrets.token_hex(8))


# ---------------------------------------------------------------- API tokens


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_api_token(
    session: AsyncSession, name: str, scopes: list[str]
) -> tuple[ApiToken, str]:
    plain = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ApiToken(name=name, token_hash=_token_hash(plain), scopes=sorted(set(scopes)))
    session.add(token)
    await session.flush()
    return token, plain


async def check_api_token(session: AsyncSession, plain: str) -> ApiToken | None:
    if not plain.startswith(TOKEN_PREFIX):
        return None
    token = await session.scalar(
        select(ApiToken).where(
            ApiToken.token_hash == _token_hash(plain), ApiToken.revoked_at.is_(None)
        )
    )
    if token is not None:
        await session.execute(
            update(ApiToken).where(ApiToken.id == token.id).values(last_used_at=func.now())
        )
    return token
