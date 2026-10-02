"""Login, logout, first-run setup, admin accounts and API tokens."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from nestris_ltm.api.auth import (
    SESSION_COOKIE,
    AdminDep,
    LoginThrottle,
    get_principal,
    is_loopback,
)
from nestris_ltm.api.deps import SessionDep
from nestris_ltm.db.models import AdminUser, ApiToken
from nestris_ltm.services import audit
from nestris_ltm.services import auth as auth_service

router = APIRouter(prefix="/api", tags=["auth"])
_throttle = LoginThrottle()


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class NewAdmin(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=256)


class PasswordChange(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class AdminOut(BaseModel):
    id: int
    username: str
    created_at: datetime
    last_login_at: datetime | None


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(min_length=1)


class TokenOut(BaseModel):
    id: int
    name: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


def _set_cookie(request: Request, response: Response, value: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        value,
        max_age=auth_service.SESSION_TTL_S,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/auth/me")
async def me(request: Request, session: SessionDep) -> dict[str, Any]:
    principal = await get_principal(request)
    needs_setup = await auth_service.admin_count(session) == 0
    return {
        "authenticated": principal is not None and principal.allows("admin"),
        "kind": principal.kind if principal else None,
        "name": principal.name if principal else None,
        "needs_setup": needs_setup,
        # Setup is only offered on the host itself.
        "can_setup": needs_setup and (is_loopback(request) or (principal is not None)),
    }


@router.post("/auth/login")
async def login(
    body: Credentials, request: Request, response: Response, session: SessionDep
) -> dict[str, Any]:
    key = request.client.host if request.client else "?"
    wait = _throttle.blocked_for(key)
    if wait > 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"too many failed logins, retry in {int(wait) + 1} s",
        )
    async with session.begin():
        user = await auth_service.authenticate(session, body.username, body.password)
        if user is None:
            _throttle.failure(key)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong username or password")
        secret = await auth_service.session_secret(session)
        cookie = auth_service.make_session_cookie(secret, user.id, user.username)
        username = user.username
    _throttle.success(key)
    _set_cookie(request, response, cookie)
    return {"ok": True, "name": username}


@router.post("/auth/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/auth/setup", status_code=status.HTTP_201_CREATED)
async def setup(
    body: NewAdmin, request: Request, response: Response, session: SessionDep
) -> dict[str, Any]:
    """Create the first admin account. Only while none exists, only on the host."""
    principal = await get_principal(request)
    if not (is_loopback(request) or (principal is not None and principal.kind == "shell")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "setup is only possible on the host")
    async with session.begin():
        # Serialize concurrent setups.
        await session.execute(select(func.pg_advisory_xact_lock(0x4E4C5355)))
        if await auth_service.admin_count(session) > 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "an admin account already exists")
        user = AdminUser(
            username=body.username, password_hash=auth_service.hash_password(body.password)
        )
        session.add(user)
        await session.flush()
        await audit.record(
            session, actor=body.username, action="create", entity="admin", entity_id=user.id
        )
        secret = await auth_service.session_secret(session)
        cookie = auth_service.make_session_cookie(secret, user.id, user.username)
    _set_cookie(request, response, cookie)
    return {"ok": True, "name": body.username}


# ---------------------------------------------------------------- admin accounts


@router.get("/admins")
async def list_admins(_: AdminDep, session: SessionDep) -> list[AdminOut]:
    rows = (await session.scalars(select(AdminUser).order_by(AdminUser.username))).all()
    return [AdminOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/admins", status_code=status.HTTP_201_CREATED)
async def create_admin(body: NewAdmin, principal: AdminDep, session: SessionDep) -> AdminOut:
    async with session.begin():
        exists = await session.scalar(
            select(AdminUser.id).where(func.lower(AdminUser.username) == body.username.lower())
        )
        if exists is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "username already taken")
        user = AdminUser(
            username=body.username, password_hash=auth_service.hash_password(body.password)
        )
        session.add(user)
        await session.flush()
        await audit.record(
            session, actor=principal.actor, action="create", entity="admin", entity_id=user.id,
            after={"username": user.username},
        )  # fmt: skip
        await session.refresh(user)
    return AdminOut.model_validate(user, from_attributes=True)


@router.put("/admins/{admin_id}/password")
async def set_admin_password(
    admin_id: int, body: PasswordChange, principal: AdminDep, session: SessionDep
) -> dict[str, bool]:
    async with session.begin():
        result = await session.execute(
            update(AdminUser)
            .where(AdminUser.id == admin_id)
            .values(password_hash=auth_service.hash_password(body.password))
        )
        if not result.rowcount:  # type: ignore[attr-defined]
            raise HTTPException(status.HTTP_404_NOT_FOUND, "admin not found")
        await audit.record(
            session, actor=principal.actor, action="password", entity="admin", entity_id=admin_id
        )
    return {"ok": True}


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: int, principal: AdminDep, session: SessionDep) -> dict[str, bool]:
    async with session.begin():
        if await auth_service.admin_count(session) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "the last admin cannot be deleted")
        user = await session.get(AdminUser, admin_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "admin not found")
        await session.delete(user)
        await audit.record(
            session, actor=principal.actor, action="delete", entity="admin", entity_id=admin_id,
            before={"username": user.username},
        )  # fmt: skip
    return {"ok": True}


# ---------------------------------------------------------------- API tokens


@router.get("/tokens")
async def list_tokens(_: AdminDep, session: SessionDep) -> list[TokenOut]:
    rows = (await session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc()))).all()
    return [TokenOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenIn, principal: AdminDep, session: SessionDep) -> dict[str, Any]:
    unknown = set(body.scopes) - set(auth_service.SCOPES)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown scopes: {sorted(unknown)}"
        )
    async with session.begin():
        token, plain = await auth_service.create_api_token(session, body.name, body.scopes)
        await audit.record(
            session, actor=principal.actor, action="create", entity="token", entity_id=token.id,
            after={"name": body.name, "scopes": sorted(body.scopes)},
        )  # fmt: skip
        await session.refresh(token)
    # The plain token is returned exactly once.
    return {"token": plain, "info": TokenOut.model_validate(token, from_attributes=True)}


@router.delete("/tokens/{token_id}")
async def revoke_token(token_id: int, principal: AdminDep, session: SessionDep) -> dict[str, bool]:
    async with session.begin():
        result = await session.execute(
            update(ApiToken)
            .where(ApiToken.id == token_id, ApiToken.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        if not result.rowcount:  # type: ignore[attr-defined]
            raise HTTPException(status.HTTP_404_NOT_FOUND, "token not found or already revoked")
        await audit.record(
            session, actor=principal.actor, action="revoke", entity="token", entity_id=token_id
        )
    return {"ok": True}


@router.get("/tokens/scopes")
async def token_scopes(_: AdminDep) -> list[str]:
    return list(auth_service.SCOPES)
