"""Abandoned domain claims expire.

This file was mostly about Preview data, and doc 07 M3's acceptance was
`"no workspace exists without a verified domain, **and Preview data expires**"`.
The second clause is gone: `doc/11` Q1 retired the unauthenticated crawl,
migration 0011 dropped `preview_session`, and with no third-party data collected
there is nothing to expire and no deletion request to answer. D9 is void.

What is left is the first clause's neighbour — a claim someone started and never
finished. It is **marked expired rather than deleted**, which is the opposite of
the rule the Preview tests enforced, and for the opposite reason: this data is
about our own user, and for a contested domain, who tried to claim it is exactly
what a support conversation needs.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

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
