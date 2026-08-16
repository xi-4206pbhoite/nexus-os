"""Database engine and session.

The engine is created lazily so the process can boot — and answer `/health` —
without a database. That matters operationally: liveness must not depend on a
dependency, or an outage becomes a restart loop.

Note what is deliberately absent. There is no `get_session()` that application
code may call freely. From M1, every read goes through `retrieval/`, which takes
a `ScopedSession` and applies the permission predicate as part of the query
(I2, I3). A bare session handed around the codebase is exactly the bypass those
invariants exist to prevent, so the accessor here is named to discourage it and
will become internal to `retrieval/` once that package exists.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.require("database_url"),
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def _unscoped_session() -> AsyncIterator[AsyncSession]:
    """A session with NO permission predicate applied.

    Only infrastructure may use this — health probes, migrations, jobs that
    operate on system tables. Never for reading customer data: that path is
    `retrieval/`, which requires a `ScopedSession`.
    """
    async with get_sessionmaker()() as session:
        yield session
