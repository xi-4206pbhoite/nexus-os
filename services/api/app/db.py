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

    # Four timeouts, and they are not redundant. `statement_timeout` bounds a
    # single query; `lock_timeout` bounds *waiting* for a lock, which the first
    # does not, because a statement blocked on a lock has not started
    # executing; `idle_in_transaction_session_timeout` bounds an open
    # transaction doing nothing, which is the shape a request that died
    # mid-flight leaves behind and the one that blocks every later migration;
    # and asyncpg's `command_timeout` is client-side, so it still fires when
    # the server is unreachable rather than merely slow.
    #
    # Before this there were none. One query that never finished held a
    # connection out of a pool of five until the process was restarted, with
    # `pool_pre_ping` reporting it healthy throughout.
    server_settings = {
        "statement_timeout": settings.db_statement_timeout,
        "lock_timeout": settings.db_lock_timeout,
        "idle_in_transaction_session_timeout": settings.db_idle_in_transaction_timeout,
        # Named in `pg_stat_activity`, so a connection can be attributed to
        # this process rather than guessed at from its query.
        "application_name": "nexus-api",
    }

    kwargs: dict[str, object] = {
        "echo": False,
        # Managed Postgres closes idle connections and can cold-start, so a
        # pooled connection may be dead by the time it is reused.
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
        # Recycle before a provider's idle timeout rather than after it.
        "pool_recycle": 300,
        # How long a request waits for a connection before failing. The default
        # is 30 seconds, which is longer than a caller will wait.
        "pool_timeout": settings.db_pool_timeout_seconds,
        "connect_args": {
            "server_settings": server_settings,
            "command_timeout": settings.db_command_timeout_seconds,
        },
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
    #
    # Explicit configuration, not a substring match on the hostname. It was
    # `if "-pooler" in url`, which is a guess: true of Neon's pooled endpoint
    # and of nothing else, so PgBouncer in front of RDS or a Cloud SQL proxy
    # left it silently false — and the failure it prevents appears only under
    # concurrency, which is the hardest possible way to find out.
    if settings.db_transaction_pooler:
        kwargs["poolclass"] = NullPool  # the pooler is doing the pooling
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_recycle", None)
        kwargs.pop("pool_timeout", None)
        # Both caches, and both in `connect_args`. `statement_cache_size` is
        # asyncpg's own; `prepared_statement_cache_size` is SQLAlchemy's, and
        # its adapter pops it from the *connect* keywords rather than accepting
        # it on the engine — so the previous `kwargs[...] = 0` raised
        # `TypeError: Invalid argument(s) 'prepared_statement_cache_size' sent
        # to create_engine()`. This whole branch had therefore never been
        # executed: nothing in the suite used a pooler URL, and production
        # connects to Neon's direct host (ADR 0008). The pooler path did not
        # merely mis-handle the cache; it could not build an engine at all.
        kwargs["connect_args"] = {
            "server_settings": server_settings,
            "command_timeout": settings.db_command_timeout_seconds,
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

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
