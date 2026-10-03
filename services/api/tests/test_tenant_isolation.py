"""Cross-tenant and cross-workspace isolation, attempted and failed.

Doc 07 M1: *"Done when cross-tenant and cross-workspace access is impossible and
there are tests that try and fail."* These are those tests. They deliberately
attempt every leak rather than asserting that the happy path works.

They run against a **real** PostgreSQL as the **real** application role. Both
matter: RLS is a database behaviour, not an application one, and a superuser or
`BYPASSRLS` role would sail through every policy — so a suite run as `postgres`
would pass while proving nothing.

The database URL is read from `.env` directly rather than through
`get_settings()`, because the hermetic fixture in `conftest.py` deliberately
pins settings to unconfigured. If no database is reachable these tests skip
loudly — a skip is visible in the run summary, whereas silently passing would
not be.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine

from tests.dburl import database_url

DB_URL = database_url()
# The real marker, declared in pyproject.toml. Previously a local
# `pytest.mark.skipif` — nine copies of it, so nine places a database suite
# could silently vanish from a green run. The skip decision now lives in
# conftest.py, which fails the session if it ever fires.
requires_db = pytest.mark.requires_db


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    # `requires_db` guarantees a database, so a missing URL here is a broken
    # harness rather than an absent one. Assert loudly instead of skipping —
    # a skip is what tests/test_ci_contract.py exists to make impossible.
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """A connection in a transaction that is always rolled back."""
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def set_workspace(conn: Connection, workspace_id: UUID | None) -> None:
    """Set the GUC the RLS policies read, as the application will per request."""
    if workspace_id is None:
        conn.execute(sa.text("SELECT set_config('nexus.workspace_id', '', true)"))
    else:
        conn.execute(
            sa.text("SELECT set_config('nexus.workspace_id', :ws, true)"),
            {"ws": str(workspace_id)},
        )


@pytest.fixture
def two_workspaces(conn: Connection) -> tuple[UUID, UUID, UUID, UUID]:
    """Two workspaces in *different* tenants, each with a membership."""
    tenant_a, tenant_b = uuid4(), uuid4()
    ws_a, ws_b = uuid4(), uuid4()
    user = uuid4()

    conn.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:a, 'Tenant A'), (:b, 'Tenant B')"),
        {"a": str(tenant_a), "b": str(tenant_b)},
    )
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(user), "e": f"iso-{user}@example.test"},
    )

    # Seeding is itself subject to WITH CHECK, so each row is written with the
    # GUC set to its own workspace — which is the first proof that the policy
    # applies to writes as well as reads.
    for tenant, ws, name in ((tenant_a, ws_a, "A"), (tenant_b, ws_b, "B")):
        set_workspace(conn, ws)
        conn.execute(
            sa.text(
                "INSERT INTO workspace (id, workspace_id, tenant_id, name)"
                " VALUES (:id, :id, :t, :n)"
            ),
            {"id": str(ws), "t": str(tenant), "n": f"Workspace {name}"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO membership (workspace_id, user_id, role) VALUES (:ws, :u, 'owner')"
            ),
            {"ws": str(ws), "u": str(user)},
        )

    return tenant_a, tenant_b, ws_a, ws_b


# ── The application role must not be able to bypass RLS ───────


@requires_db
def test_app_role_cannot_bypass_rls(conn: Connection) -> None:
    """If this fails, every other test in this file is meaningless."""
    row = conn.execute(
        sa.text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).one()
    assert row.rolsuper is False, "the app connects as a superuser — RLS is bypassed"
    assert row.rolbypassrls is False, "the app role has BYPASSRLS — RLS is bypassed"


@requires_db
def test_policies_are_forced_not_merely_enabled(conn: Connection) -> None:
    """A table's owner bypasses ENABLEd policies; migrations run as the owner."""
    rows = conn.execute(
        sa.text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
            " WHERE relname IN ('workspace','membership','persona','audit_log')"
        )
    ).all()
    assert len(rows) == 4
    for r in rows:
        assert r.relrowsecurity is True, f"{r.relname}: RLS not enabled"
        assert r.relforcerowsecurity is True, f"{r.relname}: RLS not FORCEd"


# ── Reads ─────────────────────────────────────────────────────


@requires_db
def test_cross_workspace_read_returns_nothing(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    _, _, ws_a, ws_b = two_workspaces

    set_workspace(conn, ws_a)
    visible = conn.execute(sa.text("SELECT id FROM workspace")).scalars().all()
    assert [str(v) for v in visible] == [str(ws_a)]
    assert str(ws_b) not in [str(v) for v in visible]


@requires_db
def test_cross_tenant_read_returns_nothing(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """The workspaces live in different tenants; neither may see the other."""
    _, tenant_b, ws_a, _ = two_workspaces

    set_workspace(conn, ws_a)
    rows = conn.execute(
        sa.text("SELECT id FROM workspace WHERE tenant_id = :t"), {"t": str(tenant_b)}
    ).all()
    assert rows == []


@requires_db
def test_cleared_workspace_sees_nothing(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """Default deny when the GUC is explicitly cleared to the empty string.

    This is a distinct state from "never set", and it is the one an obvious
    "clear the workspace" implementation produces. Before the policy used
    NULLIF, `''::uuid` raised — fail-closed, but a 500 on every subsequent
    query rather than a clean deny.
    """
    set_workspace(conn, None)
    assert conn.execute(sa.text("SELECT count(*) FROM workspace")).scalar() == 0
    assert conn.execute(sa.text("SELECT count(*) FROM membership")).scalar() == 0


@requires_db
def test_never_set_workspace_sees_nothing(engine: Engine) -> None:
    """Default deny on a connection where the GUC was never set at all.

    A retry worker, a scheduled job or a second service that bypasses the
    request path must see nothing rather than everything.
    """
    with engine.connect() as fresh:
        assert (
            fresh.execute(sa.text("SELECT current_setting('nexus.workspace_id', true)")).scalar()
            is None
        )
        assert fresh.execute(sa.text("SELECT count(*) FROM workspace")).scalar() == 0
        assert fresh.execute(sa.text("SELECT count(*) FROM membership")).scalar() == 0


@requires_db
def test_aggregates_do_not_leak_across_workspaces(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """A count is a function of the values; it must respect the same filter.

    Doc 06 §4.5: titles, counts and metadata of filtered results are not
    disclosable. A leaking `count(*)` is how existence gets confirmed.
    """
    _, _, ws_a, _ = two_workspaces

    set_workspace(conn, ws_a)
    assert conn.execute(sa.text("SELECT count(*) FROM workspace")).scalar() == 1
    assert conn.execute(sa.text("SELECT count(*) FROM membership")).scalar() == 1


@requires_db
def test_targeted_read_of_a_known_id_still_fails(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """Knowing the other workspace's UUID must not help."""
    _, _, ws_a, ws_b = two_workspaces

    set_workspace(conn, ws_a)
    row = conn.execute(
        sa.text("SELECT id FROM workspace WHERE id = :id"), {"id": str(ws_b)}
    ).first()
    assert row is None


# ── Writes ────────────────────────────────────────────────────


@requires_db
def test_cannot_insert_into_another_workspace(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """WITH CHECK must stop a write aimed at someone else's workspace."""
    _, _, ws_a, ws_b = two_workspaces

    set_workspace(conn, ws_a)
    with pytest.raises(sa.exc.ProgrammingError) as exc:
        conn.execute(
            sa.text("INSERT INTO audit_log (workspace_id, action) VALUES (:ws, 'forged')"),
            {"ws": str(ws_b)},
        )
    assert "row-level security" in str(exc.value).lower()


@requires_db
def test_cannot_update_another_workspace(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    _, _, ws_a, ws_b = two_workspaces

    set_workspace(conn, ws_a)
    result = conn.execute(
        sa.text("UPDATE workspace SET name = 'hijacked' WHERE id = :id"),
        {"id": str(ws_b)},
    )
    # Invisible rows cannot be updated: the statement affects nothing.
    assert result.rowcount == 0

    set_workspace(conn, ws_b)
    name = conn.execute(
        sa.text("SELECT name FROM workspace WHERE id = :id"), {"id": str(ws_b)}
    ).scalar()
    assert name == "Workspace B"


@requires_db
def test_cannot_delete_another_workspace(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    _, _, ws_a, ws_b = two_workspaces

    set_workspace(conn, ws_a)
    result = conn.execute(
        sa.text("DELETE FROM membership WHERE workspace_id = :id"), {"id": str(ws_b)}
    )
    assert result.rowcount == 0

    set_workspace(conn, ws_b)
    assert conn.execute(sa.text("SELECT count(*) FROM membership")).scalar() == 1


# ── Workspace switch (doc 06 §2.1) ────────────────────────────


@requires_db
def test_switching_workspace_changes_visibility_immediately(
    conn: Connection, two_workspaces: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """The agency case: one identity, many workspaces, strict isolation.

    Visibility must follow the switch on the same connection — a pooled
    connection retaining the previous workspace's rows is exactly the leak
    doc 06 §2.1 warns about.
    """
    _, _, ws_a, ws_b = two_workspaces

    set_workspace(conn, ws_a)
    assert conn.execute(sa.text("SELECT name FROM workspace")).scalar() == "Workspace A"

    set_workspace(conn, ws_b)
    assert conn.execute(sa.text("SELECT name FROM workspace")).scalar() == "Workspace B"

    set_workspace(conn, ws_a)
    assert conn.execute(sa.text("SELECT name FROM workspace")).scalar() == "Workspace A"


# ── The bridge to the application's own helper (H9) ───────────


def test_scoped_connection_sets_the_same_gucs_this_suite_hand_sets() -> None:
    """H9 lists this file's hand-set GUCs as a "test mirror" to retire by
    driving `scoped_connection` instead. **It is deliberately not retired**, and
    this test is what makes that safe rather than lazy.

    The suite above asserts a *database* behaviour: that the RLS policies in
    migration 0002 isolate tenants, whatever the application does. It runs plain
    synchronous SQL as the real unprivileged role for exactly that reason — the
    same reason `pyproject.toml` carries `psycopg2-binary` as a test-only
    dependency. Routing it through `scoped_connection` would change what is
    proved from "the policy isolates" to "our helper sets a GUC", which is
    strictly weaker: a bug in the helper would then hide a working policy, and a
    missing policy would be masked by a correct helper.

    What the mirror argument *is* right about is drift — two places that name
    `nexus.workspace_id` can disagree. So the coupling is asserted here rather
    than removed: if `scoped_connection` ever sets a different GUC, or stops
    setting one, this fails and the isolation suite above is known to be
    testing something the application no longer does.
    """
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "retrieval" / "scoped.py").read_text(
        encoding="utf-8"
    )
    helper_gucs = set(re.findall(r"set_config\(\s*'([a-z_.]+)'", source))

    this_file = Path(__file__).read_text(encoding="utf-8")
    suite_gucs = set(re.findall(r"set_config\('([a-z_.]+)'", this_file))

    assert "nexus.workspace_id" in helper_gucs
    assert suite_gucs <= helper_gucs, (
        f"this suite sets {sorted(suite_gucs - helper_gucs)}, which "
        "`scoped_connection` does not — so it is proving isolation against a "
        "scope the application never establishes."
    )
