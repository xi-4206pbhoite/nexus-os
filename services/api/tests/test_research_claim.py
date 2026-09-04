"""Two workers, one run. `SELECT … FOR UPDATE SKIP LOCKED`.

This is the difference between scaling the worker out and running every research
job twice. It cannot be tested with a mock — the whole property is what
PostgreSQL does when two real transactions reach the same row, so these run
against a real database with two real connections.

The second test is resumability (Q50): a worker killed mid-run leaves a row in
`running` that nothing will finish, and a founder watching the progress screen
waits on a spinner that means nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.research import CLAIM_SQL, STALE_AFTER_MINUTES
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def _workspace(db: AsyncSession) -> tuple[UUID, UUID]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"claim-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await apply_workspace_scope(db, ws)
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"claim-{ws.hex[:8]}.om"},
    )
    await db.commit()
    return user, ws


async def _queue_run(
    db: AsyncSession, ws: UUID, *, state: str = "queued", age_mins: int = 0
) -> UUID:
    run = uuid4()
    await apply_workspace_scope(db, ws)
    await db.execute(
        sa.text(
            "INSERT INTO research_run (id, workspace_id, state, started_at)"
            " VALUES (:i, :w, :s,"
            "         CASE WHEN :age > 0 THEN now() - make_interval(mins => :age) ELSE NULL END)"
        ),
        {"i": str(run), "w": str(ws), "s": state, "age": age_mins},
    )
    await db.commit()
    return run


@requires_db
async def test_two_workers_never_claim_the_same_run(app_db: None) -> None:
    """The property `SKIP LOCKED` exists for.

    Both transactions are open at once and neither commits before the other
    runs — which is exactly the interleaving a naive SELECT-then-UPDATE gets
    wrong, because between those two statements is where the second worker
    reads the row the first is about to take.

    Without `SKIP LOCKED` the second worker would *block* here rather than
    return nothing, and then claim the same run when the lock released.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as setup:
        user, ws = await _workspace(setup)
        run = await _queue_run(setup, ws)

        try:
            async with sessionmaker() as first, sessionmaker() as second:
                await apply_workspace_scope(first, ws)
                claimed_first = (
                    await first.execute(sa.text(CLAIM_SQL), {"stale": STALE_AFTER_MINUTES})
                ).first()

                # The first transaction is still open and holding the row lock.
                await apply_workspace_scope(second, ws)
                claimed_second = (
                    await second.execute(sa.text(CLAIM_SQL), {"stale": STALE_AFTER_MINUTES})
                ).first()

                assert claimed_first is not None, "the first worker must get the run"
                assert claimed_first.id == run
                assert claimed_second is None, (
                    "the second worker must step over the locked row and find nothing — "
                    "without SKIP LOCKED it would block, then claim the same run"
                )
                await first.commit()
                await second.rollback()
        finally:
            await apply_workspace_scope(setup, ws)
            for statement in (
                "DELETE FROM research_run WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await setup.execute(sa.text(statement), {"w": str(ws)})
            await setup.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            await setup.commit()


@requires_db
async def test_a_run_orphaned_by_a_worker_restart_is_reclaimed(app_db: None) -> None:
    """Q50. A worker killed mid-run leaves `running` behind forever.

    The founder's progress screen would wait on it indefinitely, which is the
    one thing `doc/12` P11 says that screen must never do — never one spinner.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user, ws = await _workspace(db)
        try:
            fresh = await _queue_run(db, ws, state="running", age_mins=1)
            await apply_workspace_scope(db, ws)
            assert (
                await db.execute(sa.text(CLAIM_SQL), {"stale": STALE_AFTER_MINUTES})
            ).first() is None, (
                "a run that started a minute ago belongs to a worker that is still "
                "working on it — reclaiming it would put two workers on the same sources"
            )

            await db.execute(
                sa.text(
                    "UPDATE research_run SET started_at = now() - make_interval(mins => :old)"
                    " WHERE id = :i"
                ),
                {"i": str(fresh), "old": STALE_AFTER_MINUTES + 5},
            )
            await db.commit()

            await apply_workspace_scope(db, ws)
            reclaimed = (
                await db.execute(sa.text(CLAIM_SQL), {"stale": STALE_AFTER_MINUTES})
            ).first()
            assert reclaimed is not None and reclaimed.id == fresh, (
                "a run stalled past the window must be reclaimable, or it waits forever"
            )
            await db.commit()
        finally:
            await apply_workspace_scope(db, ws)
            for statement in (
                "DELETE FROM research_run WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await db.execute(sa.text(statement), {"w": str(ws)})
            await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            await db.commit()


def test_the_stale_window_is_longer_than_the_hard_crawl_cap() -> None:
    """D20 hard-stops a crawl at 10 minutes. If the reclaim window were shorter,
    every slow-but-healthy run would be stolen from the worker still running it
    — and two workers writing the same sources is worse than one finishing late."""
    assert STALE_AFTER_MINUTES > 10
