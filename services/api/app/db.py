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
from sqlalchemy.pool import NullPool

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.require("database_url")

    kwargs: dict[str, object] = {
        "echo": False,
        # Managed Postgres closes idle connections and can cold-start, so a
        # pooled connection may be dead by the time it is reused.
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
        # Recycle before a provider's idle timeout rather than after it.
        "pool_recycle": 300,
    }

    # A transaction-mode pooler (PgBouncer, and Neon's `-pooler` endpoint) hands
    # a different server connection to each transaction, so a prepared statement
    # created on one is missing on the next — asyncpg then fails with
    # "prepared statement ... does not exist" under concurrency. Disabling both
    # caches is the documented requirement.
    #
    # Our GUC-based scoping is unaffected: `set_config(..., is_local => true)` is
    # transaction-scoped, so it travels with the transaction rather than the
    # session. Session-level state would have been silently wrong here.
    if "-pooler" in url:
        kwargs["poolclass"] = NullPool  # the pooler is doing the pooling
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_recycle", None)
        kwargs["connect_args"] = {"statement_cache_size": 0}
        kwargs["prepared_statement_cache_size"] = 0

    return create_async_engine(url, **kwargs)


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
