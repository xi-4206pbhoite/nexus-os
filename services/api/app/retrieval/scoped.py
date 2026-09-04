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
from uuid import UUID

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


async def apply_workspace_scope(db: AsyncSession, workspace_id: UUID | str) -> None:
    """Set the scoping GUC on an existing transaction. **The only place it happens.**

    Every row-level security policy in this database reads
    `nexus.workspace_id`, so this one line is what turns a connection into a
    tenant. It was spelled out in ten modules; now they call this, and there is
    one function to audit instead of ten near-identical strings that could drift
    apart without anything noticing.

    Separate from `scoped_connection` because the callers have different
    transaction shapes and that is not a defect to be flattened: registration
    scopes to a workspace it created moments earlier in the same transaction,
    the audit writer must join the caller's transaction rather than open its
    own, and session resolution runs before any workspace is known. A
    `scoped_connection` that quietly opened a second transaction would break
    atomicity in exactly the places that most need it.

    Takes `UUID | str` because callers legitimately hold both — a route has the
    session's `UUID`, a registration has the string it just generated — and
    making each of them convert would put a `str()` at ten call sites for the
    benefit of one signature.

    `true` — transaction-local. It dies with the transaction, so it cannot
    survive onto a pooled connection and silently scope the next request to the
    previous caller's company. That is the failure this argument prevents, and
    it would look like data appearing where it does not belong rather than like
    an error.
    """
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )
