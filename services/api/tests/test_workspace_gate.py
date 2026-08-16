"""No workspace exists without a verified domain.

Doc 07 M3's acceptance, and its validation step: *"try to create a workspace for
a domain I don't control and fail."* These are that attempt, in every shape I
could think of.

Runs against the real database, because the last line of defence is a partial
unique index rather than application logic — first verified wins is decided by
Postgres, not by our timing.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[3]


def _database_url() -> str | None:
    url = os.environ.get("NEXUS_DATABASE_URL") or ""
    if not url:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("NEXUS_DATABASE_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    if not url or "USER:PASSWORD" in url:
        return None
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)


DB_URL = _database_url()
requires_db = pytest.mark.skipif(DB_URL is None, reason="No NEXUS_DATABASE_URL")


@pytest.fixture(scope="module")
def engine():  # type: ignore[no-untyped-def]
    if DB_URL is None:
        pytest.skip("no database")
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine) -> Iterator[Connection]:  # type: ignore[no-untyped-def]
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def make_user(conn: Connection) -> UUID:
    uid = uuid4()
    conn.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i, :e)"),
        {"i": str(uid), "e": f"u-{uid}@example.com"},
    )
    return uid


def make_claim(
    conn: Connection,
    *,
    user_id: UUID,
    domain: str,
    state: str = "verified",
    method: str = "dns_txt",
    strength: str = "strong",
    verified: bool = True,
) -> UUID:
    cid = uuid4()
    conn.execute(
        text(
            "INSERT INTO domain_claim"
            " (id, domain, user_id, method, strength, challenge_token, state,"
            "  expires_at, verified_at)"
            " VALUES (:i, :d, :u, :m, :s, :c, :st, :exp, :v)"
        ),
        {
            "i": str(cid),
            "d": domain,
            "u": str(user_id),
            "m": method,
            "s": strength,
            "c": f"challenge-{cid}",
            "st": state,
            "exp": datetime.now(UTC) + timedelta(days=14),
            "v": datetime.now(UTC) if verified else None,
        },
    )
    return cid


def make_workspace(conn: Connection, *, domain: str, verified: bool = True) -> UUID:
    tenant, ws = uuid4(), uuid4()
    conn.execute(text("INSERT INTO tenant (id, name) VALUES (:i, 'T')"), {"i": str(tenant)})
    conn.execute(text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    conn.execute(
        text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i, :i, :t, 'W', :d, :v)"
        ),
        {
            "i": str(ws),
            "t": str(tenant),
            "d": domain,
            "v": datetime.now(UTC) if verified else None,
        },
    )
    return ws


# ── The database is the last line of defence ──────────────────


@requires_db
def test_two_verified_workspaces_cannot_hold_one_domain(conn: Connection) -> None:
    """First verified wins, decided by Postgres rather than by our timing.

    Two requests can pass an application-level "does it exist?" check
    simultaneously. The partial unique index is what actually resolves that.
    """
    domain = f"contested-{uuid4().hex[:8]}.om"
    make_workspace(conn, domain=domain)

    with pytest.raises(sa.exc.IntegrityError):
        make_workspace(conn, domain=domain)


@requires_db
def test_the_uniqueness_only_applies_to_verified_domains(conn: Connection) -> None:
    """An unverified placeholder must not reserve a domain.

    Otherwise typing a competitor's URL would be enough to lock them out.
    """
    domain = f"unverified-{uuid4().hex[:8]}.om"
    first = make_workspace(conn, domain=domain, verified=False)
    second = make_workspace(conn, domain=domain, verified=False)  # must not raise

    assert first != second

    # Counted one at a time, under each workspace's own GUC. A single
    # `count(*)` would be filtered by RLS to whichever workspace was set last —
    # correct behaviour, and a reminder that these rows are never visible
    # together to an ordinary caller.
    for ws in (first, second):
        conn.execute(text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
        found = (
            conn.execute(text("SELECT id FROM workspace WHERE lower(domain) = :d"), {"d": domain})
            .scalars()
            .all()
        )
        assert [str(f) for f in found] == [str(ws)]


@requires_db
def test_domain_uniqueness_is_case_insensitive(conn: Connection) -> None:
    domain = f"Case-{uuid4().hex[:8]}.OM"
    make_workspace(conn, domain=domain.lower())
    with pytest.raises(sa.exc.IntegrityError):
        make_workspace(conn, domain=domain.upper())


# ── Claim state ───────────────────────────────────────────────


@requires_db
def test_a_pending_claim_is_not_a_verified_one(conn: Connection) -> None:
    user = make_user(conn)
    domain = f"pending-{uuid4().hex[:8]}.om"
    claim = make_claim(conn, user_id=user, domain=domain, state="pending", verified=False)

    row = conn.execute(
        text("SELECT state, verified_at FROM domain_claim WHERE id = :i"), {"i": str(claim)}
    ).one()
    assert row.state == "pending"
    assert row.verified_at is None


@requires_db
def test_claim_state_is_constrained(conn: Connection) -> None:
    """An unrecognised state must not be storable — the gate compares against
    a fixed set, and a typo'd state would silently fall through it."""
    user = make_user(conn)
    with pytest.raises(sa.exc.IntegrityError):
        make_claim(conn, user_id=user, domain="x.om", state="totally-verified")


@requires_db
def test_claim_method_is_constrained(conn: Connection) -> None:
    user = make_user(conn)
    with pytest.raises(sa.exc.IntegrityError):
        make_claim(conn, user_id=user, domain="x.om", method="pinky-promise")


@requires_db
def test_claim_strength_is_constrained(conn: Connection) -> None:
    """Strength decides whether Owner-claim review is flagged."""
    user = make_user(conn)
    with pytest.raises(sa.exc.IntegrityError):
        make_claim(conn, user_id=user, domain="x.om", strength="very-strong")


@requires_db
def test_only_one_pending_claim_per_user_and_domain(conn: Connection) -> None:
    """Retrying must not leave a trail of tokens that all still work."""
    user = make_user(conn)
    domain = f"retry-{uuid4().hex[:8]}.om"
    make_claim(conn, user_id=user, domain=domain, state="pending", verified=False)
    with pytest.raises(sa.exc.IntegrityError):
        make_claim(conn, user_id=user, domain=domain, state="pending", verified=False)


@requires_db
def test_two_different_people_may_each_attempt_the_same_domain(conn: Connection) -> None:
    """Both may *try*. Only one can win, and that is decided at creation.

    Blocking the second attempt outright would let anyone deny a domain to its
    real owner simply by starting a claim first.
    """
    domain = f"shared-{uuid4().hex[:8]}.om"
    make_claim(conn, user_id=make_user(conn), domain=domain, state="pending", verified=False)
    make_claim(conn, user_id=make_user(conn), domain=domain, state="pending", verified=False)

    count = conn.execute(
        text("SELECT count(*) FROM domain_claim WHERE lower(domain) = :d"), {"d": domain}
    ).scalar()
    assert count == 2


# ── Weak claims flag review ───────────────────────────────────


@requires_db
def test_workspace_records_its_verification_method(conn: Connection) -> None:
    """Support needs to know *how* a workspace was proved, months later."""
    domain = f"method-{uuid4().hex[:8]}.om"
    ws = make_workspace(conn, domain=domain)
    conn.execute(
        text(
            "UPDATE workspace SET verification_method = 'email', owner_claim_review = true"
            " WHERE id = :i"
        ),
        {"i": str(ws)},
    )
    row = conn.execute(
        text("SELECT verification_method, owner_claim_review FROM workspace WHERE id = :i"),
        {"i": str(ws)},
    ).one()
    assert row.verification_method == "email"
    assert row.owner_claim_review is True


@requires_db
def test_owner_claim_review_defaults_to_false(conn: Connection) -> None:
    ws = make_workspace(conn, domain=f"clean-{uuid4().hex[:8]}.om")
    flagged = conn.execute(
        text("SELECT owner_claim_review FROM workspace WHERE id = :i"), {"i": str(ws)}
    ).scalar()
    assert flagged is False


# ── Re-verification and revocation ────────────────────────────


@requires_db
def test_claims_due_for_recheck_are_selectable(conn: Connection) -> None:
    """Doc 06 §1.1 requires a re-verification cadence."""
    user = make_user(conn)
    domain = f"recheck-{uuid4().hex[:8]}.om"
    claim = make_claim(conn, user_id=user, domain=domain)
    conn.execute(
        text("UPDATE domain_claim SET next_check_at = now() - interval '1 day' WHERE id = :i"),
        {"i": str(claim)},
    )

    due = (
        conn.execute(
            text(
                "SELECT id FROM domain_claim"
                " WHERE state = 'verified' AND next_check_at <= now() AND revoked_at IS NULL"
            )
        )
        .scalars()
        .all()
    )
    assert str(claim) in [str(d) for d in due]


@requires_db
def test_a_revoked_claim_stops_being_due_for_recheck(conn: Connection) -> None:
    user = make_user(conn)
    claim = make_claim(conn, user_id=user, domain=f"revoked-{uuid4().hex[:8]}.om")
    conn.execute(
        text(
            "UPDATE domain_claim"
            " SET next_check_at = now() - interval '1 day',"
            "     revoked_at = now(), state = 'revoked' WHERE id = :i"
        ),
        {"i": str(claim)},
    )

    due = (
        conn.execute(
            text(
                "SELECT id FROM domain_claim"
                " WHERE state = 'verified' AND next_check_at <= now() AND revoked_at IS NULL"
            )
        )
        .scalars()
        .all()
    )
    assert str(claim) not in [str(d) for d in due]


@requires_db
def test_revocation_does_not_delete_the_workspace(conn: Connection) -> None:
    """A DNS blip must not destroy a customer's data.

    Revocation flags the workspace for review; a human decides what happens
    next.
    """
    domain = f"lapsed-{uuid4().hex[:8]}.om"
    ws = make_workspace(conn, domain=domain)
    user = make_user(conn)
    claim = make_claim(conn, user_id=user, domain=domain)
    conn.execute(
        text("UPDATE domain_claim SET workspace_id = :w WHERE id = :i"),
        {"w": str(ws), "i": str(claim)},
    )

    conn.execute(
        text(
            "UPDATE domain_claim SET state = 'revoked', revoked_at = now(),"
            " revoked_reason = 'TXT record no longer resolves' WHERE id = :i"
        ),
        {"i": str(claim)},
    )
    conn.execute(
        text(
            "UPDATE workspace SET owner_claim_review = true"
            " WHERE id = (SELECT workspace_id FROM domain_claim WHERE id = :i)"
        ),
        {"i": str(claim)},
    )

    row = conn.execute(
        text("SELECT id, owner_claim_review FROM workspace WHERE id = :i"), {"i": str(ws)}
    ).first()
    assert row is not None, "revocation must not delete the workspace"
    assert row.owner_claim_review is True
