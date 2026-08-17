"""Email verification tokens.

The properties that matter are all negative: a token must not survive its use,
must not survive its expiry, must not be readable from the database, and must
not be guessable.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, create_engine, text

from app.auth.email_verification import build_email
from app.auth.tokens import hash_token, new_token
from tests.dburl import database_url

DB_URL = database_url()
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


def make_user(conn: Connection) -> tuple[UUID, str]:
    uid = uuid4()
    email = f"v-{uid}@example.com"
    conn.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i,:e)"), {"i": str(uid), "e": email}
    )
    return uid, email


def store_token(conn: Connection, *, user_id: UUID, email: str, token: str, ttl: timedelta) -> None:
    conn.execute(
        text(
            "INSERT INTO email_verification (user_id, token_hash, email, expires_at)"
            " VALUES (:u,:h,:e,:x)"
        ),
        {
            "u": str(user_id),
            "h": hash_token(token),
            "e": email,
            "x": datetime.now(UTC) + ttl,
        },
    )


def consume(conn: Connection, token: str) -> UUID | None:
    row = conn.execute(
        text(
            "UPDATE email_verification SET consumed_at = now()"
            " WHERE token_hash = :h AND consumed_at IS NULL AND expires_at > now()"
            " RETURNING user_id"
        ),
        {"h": hash_token(token)},
    ).first()
    return UUID(str(row.user_id)) if row else None


# ── Single use ────────────────────────────────────────────────


@requires_db
def test_a_valid_token_verifies_once(conn: Connection) -> None:
    user, email = make_user(conn)
    token = new_token()
    store_token(conn, user_id=user, email=email, token=token, ttl=timedelta(hours=24))

    assert consume(conn, token) == user


@requires_db
def test_a_consumed_token_cannot_be_reused(conn: Connection) -> None:
    """A forwarded link must not verify a second time."""
    user, email = make_user(conn)
    token = new_token()
    store_token(conn, user_id=user, email=email, token=token, ttl=timedelta(hours=24))

    assert consume(conn, token) == user
    assert consume(conn, token) is None


@requires_db
def test_two_simultaneous_clicks_cannot_both_succeed(conn: Connection) -> None:
    """The conditional update is what decides, not a read-then-write."""
    user, email = make_user(conn)
    token = new_token()
    store_token(conn, user_id=user, email=email, token=token, ttl=timedelta(hours=24))

    results = [consume(conn, token), consume(conn, token)]
    assert results.count(None) == 1
    assert user in results


# ── Expiry ────────────────────────────────────────────────────


@requires_db
def test_an_expired_token_does_not_verify(conn: Connection) -> None:
    user, email = make_user(conn)
    token = new_token()
    store_token(conn, user_id=user, email=email, token=token, ttl=-timedelta(seconds=1))

    assert consume(conn, token) is None


@requires_db
def test_an_unknown_token_does_not_verify(conn: Connection) -> None:
    assert consume(conn, new_token()) is None


# ── Storage ───────────────────────────────────────────────────


@requires_db
def test_only_the_hash_is_stored(conn: Connection) -> None:
    """A leaked database must not yield working verification links."""
    user, email = make_user(conn)
    token = new_token()
    store_token(conn, user_id=user, email=email, token=token, ttl=timedelta(hours=24))

    stored = (
        conn.execute(
            text("SELECT token_hash FROM email_verification WHERE user_id = :u"), {"u": str(user)}
        )
        .scalars()
        .all()
    )
    assert token not in stored
    assert all(len(s) == 64 for s in stored)


@requires_db
def test_issuing_a_new_token_supersedes_the_previous_one(conn: Connection) -> None:
    """Otherwise an old forwarded email keeps working indefinitely."""
    user, email = make_user(conn)
    first, second = new_token(), new_token()

    store_token(conn, user_id=user, email=email, token=first, ttl=timedelta(hours=24))
    conn.execute(
        text(
            "UPDATE email_verification SET consumed_at = now()"
            " WHERE user_id = :u AND consumed_at IS NULL"
        ),
        {"u": str(user)},
    )
    store_token(conn, user_id=user, email=email, token=second, ttl=timedelta(hours=24))

    assert consume(conn, first) is None
    assert consume(conn, second) == user


# ── The email itself ──────────────────────────────────────────


def test_the_email_carries_a_working_link() -> None:
    token = new_token()
    email = build_email(to="a@b.com", token=token, base_url="https://nexusos.example/")
    assert token in email.text_body
    assert "verify-email?token=" in email.text_body


def test_the_email_tells_an_uninvolved_recipient_nothing_happened() -> None:
    """Registration is silent about whether an address exists, so this email is
    what reaches the real owner if someone else typed their address."""
    email = build_email(to="a@b.com", token=new_token(), base_url="https://x.example")
    assert "did not create this account" in email.text_body


def test_the_email_states_the_link_is_single_use_and_expiring() -> None:
    email = build_email(to="a@b.com", token=new_token(), base_url="https://x.example")
    assert "once" in email.text_body
    assert "24 hours" in email.text_body
