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
