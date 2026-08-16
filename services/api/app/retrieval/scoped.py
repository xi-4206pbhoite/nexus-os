"""Scoped database access.

`scoped_connection` is the only way application code reaches workspace data. It
opens a transaction and sets the two GUCs the row-level security policies read,
so the permission predicate is evaluated **inside** the query plan rather than
applied afterwards (I3).

Both GUCs are set with `is_local = true`, meaning transaction-scoped. This is
load-bearing under connection pooling: a session-scoped setting would survive
the connection's return to the pool and leak the previous caller's workspace to
whoever picks it up next.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.domain.session import ScopedSession

_SET_SCOPE = text(
    """
    SELECT
        set_config('nexus.workspace_id', :workspace_id, true),
        set_config('nexus.user_id', :user_id, true)
    """
)


@asynccontextmanager
async def scoped_connection(scope: ScopedSession) -> AsyncIterator[AsyncSession]:
    """Yield a session whose every query is filtered to the caller's scope.

    Note the signature: it takes the caller's resolved authority, never
    identifiers. There is deliberately no `workspace_id: UUID` parameter — that
    would make scope something a caller could supply, which is exactly what I2
    forbids.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                _SET_SCOPE,
                {
                    "workspace_id": str(scope.workspace_id),
                    "user_id": str(scope.user_id),
                },
            )
            yield session
