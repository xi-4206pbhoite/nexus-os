"""The worker joins the pieces without losing Q56.

`crawl_site` returns instead of raising, `CLAIM_SQL` stops two workers taking
one run, `state_for` derives the run's state. This is the wiring, and wiring is
where an invariant that each piece holds individually gets dropped.

The end-to-end test is the one worth having: a real run, real rows, one source
deliberately crashing, and the other five still arriving.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.domain.research import SourceKind, SourceState
from app.research import worker_loop
from app.research.runner import CrawlOutcome
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


def test_keyword_data_is_never_estimated() -> None:
    """Q53/D2. An estimate that looks like a measurement is the one thing this
    product cannot ship — and on screen it would look exactly like the real
    thing."""
    assert "no_credentials" in worker_loop.UNAVAILABLE_NO_CREDENTIALS
    assert "unavailable" in worker_loop.UNAVAILABLE_NO_CREDENTIALS


def test_sources_do_not_all_run_at_once() -> None:
    """Six sources flat out share one outbound budget and one database pool,
    which makes the slowest slower without any of them being the bottleneck the
    founder actually feels."""
    assert 0 < worker_loop.CONCURRENT_SOURCES < len(SourceKind)


@requires_db
async def test_a_crashing_source_does_not_take_the_run_with_it(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q56, across the wiring. The crawl raises something nobody anticipated;
    the other five sources must still be written and the run must still finish.
    """

    async def explode(*_: object, **__: object) -> CrawlOutcome:
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(worker_loop, "crawl_site", explode)

    async with get_sessionmaker()() as db:
        user, tenant, ws = uuid4(), uuid4(), uuid4()
        await db.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"wl-{user.hex[:8]}@example.com"},
        )
        await db.execute(
            sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
        )
        await apply_workspace_scope(db, ws)
        await db.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                " website_url, domain_verified_at)"
                " VALUES (:i,:i,:t,'W',:d,:u, now())"
            ),
            {
                "i": str(ws),
                "t": str(tenant),
                "d": f"wl-{ws.hex[:8]}.om",
                "u": f"https://wl-{ws.hex[:8]}.om",
            },
        )
        run = uuid4()
        await db.execute(
            sa.text(
                "INSERT INTO research_run (id, workspace_id, state, requested_by_user_id)"
                " VALUES (:i,:w,'queued',:u)"
            ),
            {"i": str(run), "w": str(ws), "u": str(user)},
        )
        for kind in SourceKind:
            await db.execute(
                sa.text(
                    "INSERT INTO research_source (workspace_id, run_id, kind, state)"
                    " VALUES (:w,:r,:k,'queued')"
                ),
                {"w": str(ws), "r": str(run), "k": kind.value},
            )
        await db.commit()

        try:
            # **No scoping here, deliberately.** The worker claims as
            # `nexus_jobs`, which can see runs before it knows whose they are —
            # that is finding #25's fix (migration 0021). If this test scoped
            # the session first it would pass whether or not the grant exists,
            # and the defect it was written for would be invisible again.
            # **Claim this run specifically** (`only`).
            #
            # `CLAIM_SQL` takes the *oldest* queued run, which is right — the
            # founder who asked first is served first. It also means that on a
            # shared database this test claims somebody else's row, and the
            # assertion then quietly depends on the queue being empty, which is
            # not a state a shared database has.
            #
            # Draining was the first attempt and it deadlocked on a sourceless
            # run that re-queued itself. Narrowing the claim is the actual fix,
            # and it is a shape the worker wants anyway — `only` is finding
            # #26's resolution.
            processed = await asyncio.wait_for(
                worker_loop.process_one_run(db, only=run), timeout=180
            )
            assert processed is not None and str(processed) == str(run)

            await apply_workspace_scope(db, ws)
            rows = {
                r.kind: (r.state, r.error_reason)
                for r in (
                    await db.execute(
                        sa.text(
                            "SELECT kind, state, error_reason FROM research_source"
                            " WHERE run_id = :r"
                        ),
                        {"r": str(processed)},
                    )
                ).all()
            }

            # Every source was written, including the one that blew up.
            assert set(rows) == {k.value for k in SourceKind}
            assert rows["crawl"][0] == "failed"
            assert "rest of your research is unaffected" in rows["crawl"][1]

            # Q53/D2 — locked, not estimated.
            assert rows["keywords"][1] == worker_loop.UNAVAILABLE_NO_CREDENTIALS

            # The unbuilt sources are skipped, not failed: nothing broke, and
            # telling a founder their competitors research failed would blame
            # them for our backlog.
            assert rows["competitors"][0] == SourceState.SKIPPED.value

            # And the run itself finished rather than dying with the crawl.
            run_state = (
                await db.execute(
                    sa.text("SELECT state FROM research_run WHERE id = :i"),
                    {"i": str(processed)},
                )
            ).scalar_one()
            assert run_state in ("complete", "failed")
        finally:
            await apply_workspace_scope(db, ws)
            for statement in (
                "DELETE FROM research_source WHERE workspace_id = :w",
                "DELETE FROM research_run WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await db.execute(sa.text(statement), {"w": str(ws)})
            await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            await db.commit()
