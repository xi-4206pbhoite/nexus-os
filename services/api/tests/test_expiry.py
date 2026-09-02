"""Preview data expires.

The second half of doc 07 M3's acceptance. Doc 06 §10 requires a short TTL for
crawl data on unverified domains *and* a deletion path for the crawled company —
which has no account here.

That asymmetry is the point of these tests: the subject of this data cannot log
in, cannot see what we hold, and cannot ask anyone to remove it. Expiry must
therefore actually happen, not merely be filtered out at read time.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine, text

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
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def make_preview(
    conn: Connection,
    *,
    domain: str,
    expires_in: timedelta,
    claimed_by: UUID | None = None,
) -> UUID:
    pid = uuid4()
    conn.execute(
        text(
            "INSERT INTO preview_session"
            " (id, domain, requested_url, status, expires_at, claimed_by_workspace_id)"
            " VALUES (:i, :d, :u, 'complete', :e, :c)"
        ),
        {
            "i": str(pid),
            "d": domain,
            "u": f"https://{domain}",
            "e": datetime.now(UTC) + expires_in,
            "c": str(claimed_by) if claimed_by else None,
        },
    )
    return pid


def sweep_previews(conn: Connection) -> int:
    """Synchronous mirror of `expire_previews`."""
    return int(
        conn.execute(
            text(
                "WITH gone AS ("
                "  DELETE FROM preview_session"
                "   WHERE expires_at <= now() AND claimed_by_workspace_id IS NULL"
                "  RETURNING 1"
                ") SELECT count(*) FROM gone"
            )
        ).scalar_one()
    )


def exists(conn: Connection, pid: UUID) -> bool:
    return (
        conn.execute(text("SELECT 1 FROM preview_session WHERE id = :i"), {"i": str(pid)}).first()
        is not None
    )


# ── Expiry ────────────────────────────────────────────────────


@requires_db
def test_expired_preview_is_deleted(conn: Connection) -> None:
    pid = make_preview(conn, domain=f"old-{uuid4().hex[:8]}.om", expires_in=-timedelta(hours=1))
    assert exists(conn, pid)

    sweep_previews(conn)
    assert not exists(conn, pid), "expired Preview data must actually be removed"


@requires_db
def test_live_preview_survives(conn: Connection) -> None:
    pid = make_preview(conn, domain=f"new-{uuid4().hex[:8]}.om", expires_in=timedelta(days=7))
    sweep_previews(conn)
    assert exists(conn, pid)


@requires_db
def test_expiry_is_a_deletion_not_a_flag(conn: Connection) -> None:
    """A soft delete would leave the crawled company's data in the table
    indefinitely — the situation this exists to prevent."""
    domain = f"hard-{uuid4().hex[:8]}.om"
    make_preview(conn, domain=domain, expires_in=-timedelta(days=1))
    sweep_previews(conn)

    remaining = conn.execute(
        text("SELECT count(*) FROM preview_session WHERE lower(domain) = :d"), {"d": domain}
    ).scalar()
    assert remaining == 0


@requires_db
def test_a_claimed_preview_is_exempt(conn: Connection) -> None:
    """Once the domain is verified the data belongs to a workspace, and falls
    under that workspace's retention rather than the Preview TTL."""
    tenant, ws = uuid4(), uuid4()
    conn.execute(text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    conn.execute(text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    conn.execute(
        text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"claimed-{uuid4().hex[:8]}.om"},
    )

    pid = make_preview(
        conn,
        domain=f"claimed-{uuid4().hex[:8]}.om",
        expires_in=-timedelta(days=30),
        claimed_by=ws,
    )
    sweep_previews(conn)
    assert exists(conn, pid)


@requires_db
def test_the_sweep_is_idempotent(conn: Connection) -> None:
    make_preview(conn, domain=f"idem-{uuid4().hex[:8]}.om", expires_in=-timedelta(hours=1))
    first = sweep_previews(conn)
    second = sweep_previews(conn)
    assert first >= 1
    assert second == 0


# ── Deletion request from a company with no account ───────────


@requires_db
def test_deletion_request_removes_every_preview_for_a_domain(conn: Connection) -> None:
    """Doc 06 §10. The requester has no login here — they are the subject of
    the data, not a customer — so the request is keyed on the domain."""
    domain = f"request-{uuid4().hex[:8]}.om"
    a = make_preview(conn, domain=domain, expires_in=timedelta(days=7))
    b = make_preview(conn, domain=domain.upper(), expires_in=timedelta(days=7))
    other = make_preview(conn, domain=f"other-{uuid4().hex[:8]}.om", expires_in=timedelta(days=7))

    deleted = int(
        conn.execute(
            text(
                "WITH gone AS ("
                "  DELETE FROM preview_session"
                "   WHERE lower(domain) = lower(:d) AND claimed_by_workspace_id IS NULL"
                "  RETURNING 1"
                ") SELECT count(*) FROM gone"
            ),
            {"d": domain},
        ).scalar_one()
    )

    assert deleted == 2, "the request must match regardless of the case it was stored in"
    assert not exists(conn, a)
    assert not exists(conn, b)
    assert exists(conn, other), "another company's data must be untouched"


# ── Stale claims ──────────────────────────────────────────────


@requires_db
def test_stale_pending_claims_are_expired_not_deleted(conn: Connection) -> None:
    """The attempt stays in the audit trail: for a contested domain, who tried
    is exactly what a support conversation needs."""
    uid = uuid4()
    conn.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(uid), "e": f"u-{uid}@example.com"},
    )
    cid = uuid4()
    conn.execute(
        text(
            "INSERT INTO domain_claim"
            " (id, domain, user_id, method, strength, challenge_token, state, expires_at)"
            " VALUES (:i,:d,:u,'dns_txt','strong','tok','pending', now() - interval '1 day')"
        ),
        {"i": str(cid), "d": f"stale-{uuid4().hex[:8]}.om", "u": str(uid)},
    )

    conn.execute(
        text(
            "UPDATE domain_claim SET state = 'expired'"
            " WHERE state = 'pending' AND expires_at <= now()"
        )
    )

    state = conn.execute(
        text("SELECT state FROM domain_claim WHERE id = :i"), {"i": str(cid)}
    ).scalar()
    assert state == "expired"


@requires_db
def test_a_verified_claim_is_not_expired_by_the_sweep(conn: Connection) -> None:
    uid = uuid4()
    conn.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(uid), "e": f"u-{uid}@example.com"},
    )
    cid = uuid4()
    conn.execute(
        text(
            "INSERT INTO domain_claim"
            " (id, domain, user_id, method, strength, challenge_token, state,"
            "  expires_at, verified_at)"
            " VALUES (:i,:d,:u,'dns_txt','strong','tok','verified',"
            "         now() - interval '1 day', now())"
        ),
        {"i": str(cid), "d": f"done-{uuid4().hex[:8]}.om", "u": str(uid)},
    )

    conn.execute(
        text(
            "UPDATE domain_claim SET state = 'expired'"
            " WHERE state = 'pending' AND expires_at <= now()"
        )
    )

    state = conn.execute(
        text("SELECT state FROM domain_claim WHERE id = :i"), {"i": str(cid)}
    ).scalar()
    assert state == "verified", "a completed verification must not expire with its window"
