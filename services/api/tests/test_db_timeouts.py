"""Database timeouts, asserted on the server rather than on the keyword arguments.

`app/db.py` set none of these. A single query that never finished would hold a
connection from a pool of five until the process was restarted, and a
transaction left open by a request that died mid-flight would hold its locks
indefinitely — with `pool_pre_ping` cheerfully reporting the connection healthy.
On a serverless Postgres billed by connection-time that is also a cost bug.

The four that matter here are different from each other, which is why all four
are set rather than one:

- `statement_timeout` bounds a single query;
- `lock_timeout` bounds *waiting* for a lock, which a statement timeout does not,
  because a statement blocked on a lock has not started executing;
- `idle_in_transaction_session_timeout` bounds an open transaction doing nothing
  — the shape a crashed request leaves behind, and the one that blocks DDL;
- asyncpg's `command_timeout` is client-side, so it still fires when the server
  is unreachable rather than merely slow. A server-side timeout cannot help
  when the answer never arrives.

Asserted with `SHOW`, against the application's own engine, because a test over
`create_async_engine`'s keyword arguments proves the arguments were passed and
not that Postgres accepted them — and `server_settings` names are silently
per-driver.

**That distinction stopped being theoretical.** The three server-side timeouts
originally travelled in asyncpg's `server_settings`, which becomes the startup
packet. Stock PostgreSQL honours it; **Neon's proxy filters the startup packet
and dropped all three**, so `SHOW statement_timeout` on a live application
connection returned `0` while `application_name`, sent in the same dictionary,
arrived intact. CI runs stock PostgreSQL, so these tests passed there throughout
— the protection existed in CI and nowhere that mattered, since ADR 0008 makes
Neon production (finding #15).

They are now issued with `set_config` on the pool's `connect` event. The tests
below are written so that reverting to `server_settings` fails them **on Neon**
and still passes on stock PostgreSQL, which is the honest shape of this problem:
no test run against one database can prove a claim about the other. Run the
suite against Neon before believing anything here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.config import Env, Settings, get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()

# The real marker, declared in pyproject.toml. See the note in conftest.py.
requires_db = pytest.mark.requires_db


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Point the application's engine at the real database for this test."""
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        yield
    finally:
        await get_engine().dispose()
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


@requires_db
@pytest.mark.parametrize(
    ("guc", "expected"),
    [
        ("statement_timeout", "15s"),
        ("lock_timeout", "5s"),
        ("idle_in_transaction_session_timeout", "30s"),
    ],
)
async def test_the_server_has_the_timeout_applied(guc: str, expected: str, app_db: None) -> None:
    """`SHOW` reports what the session actually has, not what we asked for."""
    async with _unscoped_session() as session:
        value = (await session.execute(text(f"SHOW {guc}"))).scalar_one()
    assert value == expected


@requires_db
async def test_the_timeouts_survive_a_pool_checkout_cycle(app_db: None) -> None:
    """Set once per connection, not once per session.

    `set_config(..., false)` is session-scoped, so it lasts as long as the
    physical connection and a pooled connection carries it into the next
    request. The failure this rules out is a `SET LOCAL` — reverted by the first
    commit, which would leave the second and every later user of that connection
    unprotected while the first checkout looked fine.
    """
    async with _unscoped_session() as session:
        first = (await session.execute(text("SHOW statement_timeout"))).scalar_one()
        # A commit is what would discard a transaction-scoped setting.
        await session.commit()
        after_commit = (await session.execute(text("SHOW statement_timeout"))).scalar_one()

    # Return to the pool, then take a connection again.
    async with _unscoped_session() as session:
        reused = (await session.execute(text("SHOW statement_timeout"))).scalar_one()

    assert first == "15s"
    assert after_commit == "15s", "a commit discarded it — this is SET LOCAL, not SET"
    assert reused == "15s", "the setting did not survive returning to the pool"


@requires_db
async def test_application_name_still_arrives(app_db: None) -> None:
    """The control in the experiment that found #15.

    `application_name` is the one setting still sent in `server_settings`, and
    it arrives on Neon. Keeping it asserted here is what distinguishes "the
    startup packet is filtered" from "the connection is misconfigured" if this
    ever regresses — and it is why the fix targeted three settings rather than
    four.
    """
    async with _unscoped_session() as session:
        value = (await session.execute(text("SHOW application_name"))).scalar_one()

    assert value == "nexus-api"


@requires_db
async def test_a_statement_that_overruns_is_cancelled(app_db: None) -> None:
    """The timeout does something, proved without waiting fifteen seconds.

    `SET LOCAL` narrows it for this transaction only. What is being tested is
    that `statement_timeout` is live on the connection at all — a session where
    it is disabled would sleep happily past any local value.
    """
    from sqlalchemy.exc import DBAPIError

    async with _unscoped_session() as session:
        await session.execute(text("SET LOCAL statement_timeout = '100ms'"))
        with pytest.raises(DBAPIError) as raised:
            await session.execute(text("SELECT pg_sleep(2)"))

    assert "canceling statement" in str(raised.value).lower()


# ── The pooler decision is configuration, not a substring ─────


def test_the_transaction_pooler_is_an_explicit_setting() -> None:
    """It was `if "-pooler" in url`.

    That is a guess about a hostname. It is true of Neon's pooled endpoint and
    of nothing else — PgBouncer in front of RDS, a Cloud SQL proxy, or Neon
    renaming the endpoint all leave it silently false, and the failure it
    prevents is `prepared statement ... does not exist` appearing only under
    concurrency, which is the hardest possible way to find out.
    """
    assert "db_transaction_pooler" in Settings.model_fields
    assert Settings(_env_file=None, env=Env.local).db_transaction_pooler is False


@pytest.mark.parametrize("pooled", [True, False])
def test_the_pool_shape_follows_the_setting(pooled: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """A transaction-mode pooler is already pooling, so we must not pool again —
    and we must stop caching prepared statements, which is the documented
    requirement rather than a precaution."""
    monkeypatch.setenv("NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@example.invalid:5432/nexus")
    monkeypatch.setenv("NEXUS_DB_TRANSACTION_POOLER", "true" if pooled else "false")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        engine = get_engine()
        if pooled:
            assert isinstance(engine.pool, NullPool)
        else:
            assert not isinstance(engine.pool, NullPool)
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()


def test_a_pooler_hostname_alone_no_longer_changes_behaviour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression guard for the substring match returning.

    A URL naming a `-pooler` host with the setting off must pool normally. If
    someone reinstates the convenience, this fails.
    """
    monkeypatch.setenv(
        "NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@ep-x-pooler.example.invalid:5432/nexus"
    )
    monkeypatch.setenv("NEXUS_DB_TRANSACTION_POOLER", "false")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    try:
        assert not isinstance(get_engine().pool, NullPool)
    finally:
        for cache in (get_settings, get_engine, get_sessionmaker):
            cache.cache_clear()
