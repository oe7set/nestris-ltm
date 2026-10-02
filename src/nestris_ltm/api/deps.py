"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from nestris_ltm.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_runtime(request).db.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
