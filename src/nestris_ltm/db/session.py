"""Async engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nestris_ltm.config import DatabaseSettings


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        settings.url(),
        pool_size=settings.pool_size,
        max_overflow=settings.pool_size,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.connect_timeout_s,
            "server_settings": {"application_name": "nestris-ltm"},
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
