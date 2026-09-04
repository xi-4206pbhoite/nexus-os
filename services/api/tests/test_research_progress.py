"""Never one spinner (Q57).

A single spinner over six independent sources is a lie of omission: it says
"working" while the crawl has already failed, the connector was skipped, and
only keywords are still going. The founder cannot tell whether to wait, to fix
something, or to walk away.

These assert the shape that makes that impossible — every source visible, every
failure carrying its reason, and the run's own state derived rather than read.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
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


async def _cleanup(ws: UUID, user: UUID) -> None:
    from app.retrieval.scoped import apply_workspace_scope

    async with get_sessionmaker()() as db:
        await apply_workspace_scope(db, ws)
        for statement in (
            "DELETE FROM research_source WHERE workspace_id = :w",
            "DELETE FROM research_run WHERE workspace_id = :w",
            "DELETE FROM workspace WHERE id = :w",
        ):
            await db.execute(sa.text(statement), {"w": str(ws)})
        await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
        await db.commit()


async def _fixture(db: AsyncSession) -> tuple[UUID, UUID, UUID]:
    from app.retrieval.scoped import apply_workspace_scope

    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"prog-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await apply_workspace_scope(db, ws)
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"prog-{ws.hex[:8]}.om"},
    )
    run = uuid4()
    await db.execute(
        sa.text("INSERT INTO research_run (id, workspace_id, state) VALUES (:i,:w,'running')"),
        {"i": str(run), "w": str(ws)},
    )
    # The mixed reality this endpoint exists for: one failed, one skipped, one
    # unreadable, one still going. A spinner would show none of it.
    for kind, state, reason in (
        ("crawl", "js_rendered", ""),
        ("audit", "failed", "The site did not respond within 10 seconds."),
        ("competitors", "skipped", ""),
        ("keywords", "running", ""),
    ):
        await db.execute(
            sa.text(
                "INSERT INTO research_source (workspace_id, run_id, kind, state, error_reason)"
                " VALUES (:w,:r,:k,:s,:e)"
            ),
            {"w": str(ws), "r": str(run), "k": kind, "s": state, "e": reason},
        )
    await db.commit()
    return user, ws, run


def _setup() -> tuple[UUID, UUID, UUID]:
    """Run the async setup in **its own loop, then dispose the engine.**

    `TestClient` drives its own event loop, and an asyncpg connection is bound to
    the loop that opened it — a pooled connection left over from an outer loop
    surfaces as "attached to a different loop" from inside Starlette's
    middleware, naming neither the pool nor the fixture. Every other TestClient
    test in this repo is sync for the same reason; this follows them.
    """
    import asyncio

    async def run() -> tuple[UUID, UUID, UUID]:
        async with get_sessionmaker()() as db:
            result = await _fixture(db)
        await get_engine().dispose()
        return result

    return asyncio.run(run())


def _teardown(ws: UUID, user: UUID) -> None:
    import asyncio

    async def run() -> None:
        await _cleanup(ws, user)
        await get_engine().dispose()

    asyncio.run(run())


@requires_db
def test_every_source_reports_its_own_outcome(app_db: None) -> None:
    from fastapi.testclient import TestClient

    from app.deps import current_scope
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession
    from app.main import create_app

    # The session must be **closed** before `TestClient` runs. It drives its own
    # event loop, and an asyncpg connection is bound to the loop that opened it —
    # holding one open here produces "attached to a different loop" from inside
    # Starlette's middleware, which names neither the session nor the fixture.
    user, ws, run = _setup()

    try:
        if True:
            app = create_app()
            app.dependency_overrides[current_scope] = lambda: ScopedSession(
                user_id=user,
                tenant_id=uuid4(),
                workspace_id=ws,
                role=Role.OWNER,
                departments=frozenset(Department),
            )
            with TestClient(app) as client:
                body = client.get(f"/research/{run}").json()

            by_kind = {s["kind"]: s for s in body["sources"]}
            assert set(by_kind) == {"crawl", "audit", "competitors", "keywords"}

            # The whole point: four different truths, four different states.
            assert by_kind["crawl"]["state"] == "js_rendered"
            assert by_kind["competitors"]["state"] == "skipped"
            assert by_kind["keywords"]["state"] == "running"

            # A failure a founder can act on, not the word "failed".
            assert by_kind["audit"]["state"] == "failed"
            assert "did not respond" in by_kind["audit"]["error_reason"]

            # Everything that did not fail carries no reason, so a screen can
            # trust the field without checking the state first.
            for kind in ("crawl", "competitors", "keywords"):
                assert by_kind[kind]["error_reason"] == ""

            # Derived, not read. The row says `running`; so does the derivation
            # here, but only because keywords is — and it will say `complete`
            # when keywords finishes, without anything updating the run row.
            assert body["state"] == "running"
            assert body["still_running"] == 1

            app.dependency_overrides.clear()
    finally:
        _teardown(ws, user)


@requires_db
def test_a_run_from_another_workspace_is_not_found(app_db: None) -> None:
    """404, not 403. "That run exists and is not yours" confirms another company
    is using the product and roughly when."""
    from fastapi.testclient import TestClient

    from app.deps import current_scope
    from app.domain.scopes import Department, Role
    from app.domain.session import ScopedSession
    from app.main import create_app

    # The session must be **closed** before `TestClient` runs. It drives its own
    # event loop, and an asyncpg connection is bound to the loop that opened it —
    # holding one open here produces "attached to a different loop" from inside
    # Starlette's middleware, which names neither the session nor the fixture.
    user, ws, run = _setup()

    try:
        if True:
            app = create_app()
            app.dependency_overrides[current_scope] = lambda: ScopedSession(
                user_id=uuid4(),
                tenant_id=uuid4(),
                workspace_id=uuid4(),  # somebody else entirely
                role=Role.OWNER,
                departments=frozenset(Department),
            )
            with TestClient(app) as client:
                assert client.get(f"/research/{run}").status_code == 404
            app.dependency_overrides.clear()
    finally:
        _teardown(ws, user)
