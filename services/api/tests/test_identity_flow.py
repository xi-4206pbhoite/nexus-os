"""Phase 3 — identity: delivery, reset, and one company per person.

Three properties, and all three are the kind that pass by accident if you assert
the happy path only:

1. **Registering actually sends something.** `send_verification` existed with
   zero callers for two milestones, so `email_verified_at` could never be set
   and the EMAIL domain-verification method was structurally dead. A test that
   only checks the 201 would not have noticed for a third.
2. **Password reset tells an attacker nothing.** Not "returns a vague message" —
   *byte-identical* responses for a real and a fake address, and no timing
   asymmetry from the send.
3. **One person belongs to one company.** `doc/11` §3.2. Enforced where the
   write happens, not at the routes that call it, so there is one place to
   attack and one place to audit.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from email import message_from_bytes
from email.policy import default as default_policy
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.main import create_app
from tests.dburl import async_database_url, database_url

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "a-different-correct-horse-staple"
SIGNING_SECRET = "test-signing-secret-not-a-real-one"

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """A plain connection — **no** enclosing transaction to roll back.

    The usual fixture in this suite wraps each test in a transaction and rolls
    it back. That is unavailable here: these tests drive the application, which
    commits on its own connections, so nothing this connection rolls back would
    undo them. Rolling back anyway raised `SAWarning: transaction already
    deassociated from connection` once a cleanup committed inside it, and
    `filterwarnings = ["error"]` turned that into a failure.

    Isolation comes from every address being unique per test instead, and each
    test deletes the account it made.
    """
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def mail_root(tmp_path: Path) -> Path:
    root = tmp_path / "mail"
    root.mkdir()
    return root


@pytest.fixture
def api_env(mail_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the application at the real database and a temp `.mail/`."""
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("NEXUS_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("NEXUS_MAILER_BACKEND", "file")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        yield
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


@pytest.fixture
async def app_db(api_env: None) -> AsyncIterator[None]:
    """For tests that call application code directly rather than over HTTP.

    The engine must be disposed on the loop that opened its connections.
    `TestClient` does that through the app's own `lifespan`; a test that skips
    the client has to do it itself, or asyncpg transports are collected on a
    closed loop and `filterwarnings = ["error"]` fails whichever test runs next
    with `RuntimeError: Event loop is closed`. That is not hypothetical — it is
    what the first version of this file did.
    """
    yield
    await get_engine().dispose()


@pytest.fixture
def client(mail_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Path]]:
    """The application, writing to the real database and a temp `.mail/`.

    The engine is disposed by the application's own `lifespan` shutdown, which
    `TestClient.__exit__` runs — see the note in `test_document_upload_db.py`.
    Disposing from the fixture leaves asyncpg transports to be collected on a
    closed loop, and `filterwarnings = ["error"]` turns that into a failure of
    whichever test runs next.
    """
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("NEXUS_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("NEXUS_MAILER_BACKEND", "file")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()

    try:
        with TestClient(create_app()) as c:
            yield c, mail_root
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def a_fresh_address() -> str:
    return f"p3-{uuid4().hex[:12]}@example.com"


def bodies_of(mail_root: Path) -> list[str]:
    """Every message written, as text. The local equivalent of opening mailpit."""
    out = []
    for path in sorted(mail_root.glob("*.eml")):
        # `policy=default` is what makes this an `EmailMessage` with
        # `get_body`; the compat32 default returns a bare `Message`.
        message = message_from_bytes(path.read_bytes(), policy=default_policy)
        body = message.get_body(preferencelist=("plain",))
        assert body is not None, "every message must have a text/plain part"
        out.append(str(body.get_content()))
    return out


def token_in(body: str, *, path: str) -> str:
    found = re.search(rf"{re.escape(path)}\?token=([A-Za-z0-9_-]+)", body)
    assert found is not None, f"no {path} link in:\n{body}"
    return found.group(1)


def cleanup_user(conn: Connection, email: str) -> None:
    conn.execute(sa.text("DELETE FROM app_user WHERE lower(email) = lower(:e)"), {"e": email})
    conn.commit()


# ── 1. Registering sends a verification email ─────────────────


@requires_db
def test_registration_sends_verification(client: tuple[TestClient, Path], conn: Connection) -> None:
    """The whole point of Phase 3, and it is asserted through the app.

    Not "the function works" — `test_email_verification.py` already proves the
    token machinery. This proves something *calls* it, which is exactly what was
    missing.
    """
    api, mail_root = client
    email = a_fresh_address()

    try:
        response = api.post("/auth/register", json={"email": email, "password": PASSWORD})
        assert response.status_code == 201

        messages = bodies_of(mail_root)
        assert len(messages) == 1, "registering must send exactly one email"

        token = token_in(messages[0], path="/verify-email")

        stored = conn.execute(
            sa.text(
                "SELECT ev.consumed_at, u.email_verified_at"
                "  FROM email_verification ev JOIN app_user u ON u.id = ev.user_id"
                " WHERE lower(ev.email) = lower(:e)"
            ),
            {"e": email},
        ).first()
        assert stored is not None, "a verification row must exist in the database"
        assert stored.consumed_at is None
        assert stored.email_verified_at is None, "registering must not self-verify"

        # The token in the email is the one that works, and it works once.
        assert api.post("/auth/verify-email", json={"token": token}).status_code == 200

        verified = conn.execute(
            sa.text("SELECT email_verified_at FROM app_user WHERE lower(email) = lower(:e)"),
            {"e": email},
        ).scalar()
        assert verified is not None, "consuming the token must set email_verified_at"

        assert api.post("/auth/verify-email", json={"token": token}).status_code == 400
    finally:
        cleanup_user(conn, email)


@requires_db
def test_registering_a_known_address_still_answers_identically(
    client: tuple[TestClient, Path], conn: Connection
) -> None:
    """Delivery must not reintroduce the enumeration oracle registration
    already closed. The second attempt sends nothing — the real owner is told
    once — but the caller cannot tell."""
    api, mail_root = client
    email = a_fresh_address()

    try:
        first = api.post("/auth/register", json={"email": email, "password": PASSWORD})
        second = api.post("/auth/register", json={"email": email, "password": PASSWORD})

        assert first.status_code == second.status_code
        assert first.content == second.content
        assert len(bodies_of(mail_root)) == 1, "a duplicate registration must not re-send"
    finally:
        cleanup_user(conn, email)


# ── 2. Password reset reveals nothing ─────────────────────────


@requires_db
def test_password_reset_does_not_reveal_whether_an_account_exists(
    client: tuple[TestClient, Path], conn: Connection
) -> None:
    """Byte-identical, not merely similar.

    A difference of one word, one header, or one status code is a complete
    account-enumeration oracle — and this endpoint is unauthenticated, so it is
    the cheapest one in the product to query.
    """
    api, mail_root = client
    known, unknown = a_fresh_address(), a_fresh_address()

    try:
        api.post("/auth/register", json={"email": known, "password": PASSWORD})

        real = api.post("/auth/password-reset/request", json={"email": known})
        fake = api.post("/auth/password-reset/request", json={"email": unknown})

        assert real.status_code == fake.status_code
        assert real.content == fake.content, "the bodies differ — this is an oracle"
        assert dict(real.headers) == dict(fake.headers) or {
            k: v for k, v in real.headers.items() if k.lower() not in _VARYING_HEADERS
        } == {k: v for k, v in fake.headers.items() if k.lower() not in _VARYING_HEADERS}

        # And the asymmetry that response bodies cannot show: only one produced
        # an email. Registration sent one, so the reset for the known address is
        # the second message and the unknown address adds nothing.
        assert len(bodies_of(mail_root)) == 2
    finally:
        cleanup_user(conn, known)


# `date` moves between two requests and `x-request-id` is per-request by design.
_VARYING_HEADERS = {"date", "x-request-id", "content-length"}


@requires_db
def test_a_reset_token_changes_the_password_once(
    client: tuple[TestClient, Path], conn: Connection
) -> None:
    api, mail_root = client
    email = a_fresh_address()

    try:
        api.post("/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/auth/password-reset/request", json={"email": email})

        token = token_in(bodies_of(mail_root)[-1], path="/reset-password")

        confirmed = api.post(
            "/auth/password-reset/confirm",
            json={"token": token, "password": NEW_PASSWORD},
        )
        assert confirmed.status_code == 200

        assert (
            api.post("/auth/login", json={"email": email, "password": NEW_PASSWORD}).status_code
            == 200
        )
        assert (
            api.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
        ), "the old password must stop working"

        assert (
            api.post(
                "/auth/password-reset/confirm",
                json={"token": token, "password": NEW_PASSWORD},
            ).status_code
            == 400
        ), "a reset token must be single-use"
    finally:
        cleanup_user(conn, email)


@requires_db
def test_a_reset_revokes_every_live_session(
    client: tuple[TestClient, Path], conn: Connection
) -> None:
    """The reason to reset a password is usually that someone else has it.

    Leaving their session alive makes the reset a formality — they keep the
    access the reset was performed to remove.
    """
    api, mail_root = client
    email = a_fresh_address()

    try:
        api.post("/auth/register", json={"email": email, "password": PASSWORD})
        signed_in = api.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert signed_in.status_code == 200
        assert api.get("/auth/session").status_code == 200

        api.post("/auth/password-reset/request", json={"email": email})
        token = token_in(bodies_of(mail_root)[-1], path="/reset-password")
        api.post(
            "/auth/password-reset/confirm",
            json={"token": token, "password": NEW_PASSWORD},
        )

        assert api.get("/auth/session").status_code == 401, (
            "a live session survived the reset that was meant to end it"
        )
    finally:
        cleanup_user(conn, email)


# ── 3. One person, one company ────────────────────────────────


@requires_db
async def test_one_live_membership_per_user(app_db: None) -> None:
    """`doc/11` §3.2, enforced at the write rather than at the routes.

    The `membership` table stays many-to-many — the reversal is a *rule*, not a
    schema change, because the agency case in doc 06 §2.1 may come back and a
    unique index would have to be migrated away again.

    Calls the real guard on the application's own session. An earlier version of
    this test re-implemented the count in synchronous SQL so it could reuse the
    rollback fixture, which would have made it a fourth entry on H9's list of
    test mirrors — a test that passes over a copy of the logic proves the copy.
    """
    from app.db import _unscoped_session
    from app.domain.membership import UserAlreadyInAWorkspaceError, assert_no_live_membership

    user, tenant, workspace = uuid4(), uuid4(), uuid4()

    async with _unscoped_session() as db:
        try:
            await db.execute(
                sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
                {"i": str(user), "e": f"solo-{user.hex[:8]}@example.com"},
            )
            await db.execute(
                sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
            )
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(workspace)},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                    " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
                ),
                {"i": str(workspace), "t": str(tenant), "d": f"solo-{workspace.hex[:8]}.om"},
            )
            await db.commit()

            # No membership yet — the guard permits.
            await assert_no_live_membership(db, user_id=user)

            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(workspace)},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO membership (workspace_id, user_id, role) VALUES (:w,:u,'owner')"
                ),
                {"w": str(workspace), "u": str(user)},
            )
            await db.commit()

            with pytest.raises(UserAlreadyInAWorkspaceError):
                await assert_no_live_membership(db, user_id=user)
        finally:
            await db.rollback()
            for statement in (
                "DELETE FROM membership WHERE user_id = :u",
                "DELETE FROM workspace WHERE id = :w",
                "DELETE FROM tenant WHERE id = :t",
                "DELETE FROM app_user WHERE id = :u",
            ):
                await db.execute(
                    sa.text(statement), {"u": str(user), "w": str(workspace), "t": str(tenant)}
                )
            await db.commit()


@requires_db
async def test_the_guard_ignores_a_revoked_membership(app_db: None) -> None:
    """ "Live" is the load-bearing word.

    Someone who left a company must be able to join or start another. Counting
    every row ever written would lock them out permanently, and the support
    conversation that follows has no fix short of a manual DELETE.
    """
    from app.db import _unscoped_session
    from app.domain.membership import assert_no_live_membership

    user, tenant, workspace = uuid4(), uuid4(), uuid4()

    async with _unscoped_session() as db:
        try:
            await db.execute(
                sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
                {"i": str(user), "e": f"left-{user.hex[:8]}@example.com"},
            )
            await db.execute(
                sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
            )
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(workspace)},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                    " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
                ),
                {"i": str(workspace), "t": str(tenant), "d": f"left-{workspace.hex[:8]}.om"},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO membership (workspace_id, user_id, role, revoked_at)"
                    " VALUES (:w,:u,'owner', now())"
                ),
                {"w": str(workspace), "u": str(user)},
            )
            await db.commit()

            await assert_no_live_membership(db, user_id=user)
        finally:
            await db.rollback()
            for statement in (
                "DELETE FROM membership WHERE user_id = :u",
                "DELETE FROM workspace WHERE id = :w",
                "DELETE FROM tenant WHERE id = :t",
                "DELETE FROM app_user WHERE id = :u",
            ):
                await db.execute(
                    sa.text(statement), {"u": str(user), "w": str(workspace), "t": str(tenant)}
                )
            await db.commit()


@requires_db
async def test_the_guard_ignores_the_users_own_workspace(app_db: None) -> None:
    """`other_than` — the difference between a rule and a trap.

    Accepting an invitation is idempotent by design: the insert is
    `ON CONFLICT DO NOTHING`, so re-clicking a link keeps the role you already
    hold rather than resetting it (doc 06 §4.15 — a role change is not an
    invitation). Counting the user's *own* workspace would turn every second
    click into "you are already part of a company": true, useless, and refusing
    the one case that was deliberately built to be safe.

    The first version of the guard omitted the parameter and
    `test_an_existing_member_keeps_the_role_they_already_hold` failed in CI. It
    is asserted here too, because that test is about roles and would not
    obviously be the place a later reader looks for this rule.
    """
    from app.db import _unscoped_session
    from app.domain.membership import assert_no_live_membership

    user, tenant, workspace = uuid4(), uuid4(), uuid4()

    async with _unscoped_session() as db:
        try:
            await db.execute(
                sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
                {"i": str(user), "e": f"same-{user.hex[:8]}@example.com"},
            )
            await db.execute(
                sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)}
            )
            await db.execute(
                sa.text("SELECT set_config('nexus.workspace_id', :w, true)"),
                {"w": str(workspace)},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
                    " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
                ),
                {"i": str(workspace), "t": str(tenant), "d": f"same-{workspace.hex[:8]}.om"},
            )
            await db.execute(
                sa.text(
                    "INSERT INTO membership (workspace_id, user_id, role) VALUES (:w,:u,'owner')"
                ),
                {"w": str(workspace), "u": str(user)},
            )
            await db.commit()

            # Their own workspace is excluded, so this permits.
            await assert_no_live_membership(db, user_id=user, other_than=workspace)

            # Any other workspace is not.
            with pytest.raises(Exception, match="already part of a company"):
                await assert_no_live_membership(db, user_id=user, other_than=uuid4())
        finally:
            await db.rollback()
            for statement in (
                "DELETE FROM membership WHERE user_id = :u",
                "DELETE FROM workspace WHERE id = :w",
                "DELETE FROM tenant WHERE id = :t",
                "DELETE FROM app_user WHERE id = :u",
            ):
                await db.execute(
                    sa.text(statement), {"u": str(user), "w": str(workspace), "t": str(tenant)}
                )
            await db.commit()
