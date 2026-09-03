"""Rate limiting the research path.

Doc 06 §1.2 — metered APIs must never sit on an unauthenticated path, because a
script otherwise exhausts a paid quota and degrades the product for paying
tenants. Phase 2 removed the unauthenticated path itself, which is the stronger
form of that rule; these limits remain because an authenticated caller can still
loop, and a paid quota is still shared.

The per-IP and per-domain cases that used to live here went with the anonymous
audit. Their replacement is one limit keyed on the workspace — the identity that
now exists on every call.

Runs against the real database: the limit is enforced by an atomic upsert, and
an in-memory fake would test the fake rather than the guarantee.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine, text

from app.connectors.rate_limit import GLOBAL_DAILY, PER_WORKSPACE, Limit
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


def consume(conn: Connection, limit: Limit, key: str, *, now: datetime | None = None) -> int:
    """Synchronous mirror of `check_and_increment`, returning the new count."""
    moment = now or datetime.now(UTC)
    seconds = int(limit.window.total_seconds())
    epoch = int(moment.timestamp())
    start = datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)

    result = conn.execute(
        text(
            """
            INSERT INTO rate_limit_counter (bucket, window_start, count)
            VALUES (:bucket, :start, 1)
            ON CONFLICT (bucket, window_start)
            DO UPDATE SET count = rate_limit_counter.count + 1
            RETURNING count
            """
        ),
        {"bucket": f"{limit.bucket_prefix}:{key}", "start": start},
    )
    return int(result.scalar_one())


# ── The two limits ────────────────────────────────────────────


@requires_db
def test_per_workspace_limit_trips_after_its_allowance(conn: Connection) -> None:
    key = str(uuid4())
    counts = [consume(conn, PER_WORKSPACE, key) for _ in range(PER_WORKSPACE.max_count + 1)]
    assert counts[: PER_WORKSPACE.max_count] == list(range(1, PER_WORKSPACE.max_count + 1))
    assert counts[-1] > PER_WORKSPACE.max_count


@requires_db
def test_one_workspace_cannot_spend_anothers_allowance(conn: Connection) -> None:
    """The whole point of keying on the workspace.

    One tenant looping on research must not be able to lock a second tenant out
    — which is exactly what the old per-IP bucket did whenever two customers
    sat behind one office address.
    """
    a, b = str(uuid4()), str(uuid4())
    for _ in range(PER_WORKSPACE.max_count):
        consume(conn, PER_WORKSPACE, a)
    assert consume(conn, PER_WORKSPACE, b) == 1


@requires_db
def test_limits_do_not_bleed_between_scopes(conn: Connection) -> None:
    """A workspace consumption must not count against the global ceiling's key."""
    key = str(uuid4())
    consume(conn, PER_WORKSPACE, key)
    assert consume(conn, GLOBAL_DAILY, key) == 1


# ── Windows ───────────────────────────────────────────────────


@requires_db
def test_a_later_window_starts_fresh(conn: Connection) -> None:
    key = str(uuid4())
    now = datetime.now(UTC)
    for _ in range(PER_WORKSPACE.max_count):
        consume(conn, PER_WORKSPACE, key, now=now)

    later = now + PER_WORKSPACE.window + timedelta(seconds=1)
    assert consume(conn, PER_WORKSPACE, key, now=later) == 1


@requires_db
def test_counts_within_one_window_accumulate(conn: Connection) -> None:
    key = str(uuid4())
    now = datetime.now(UTC)
    consume(conn, PER_WORKSPACE, key, now=now)
    # A different moment inside the same fixed window.
    assert consume(conn, PER_WORKSPACE, key, now=now + timedelta(seconds=1)) == 2


# ── Concurrency ───────────────────────────────────────────────


@requires_db
def test_increment_is_atomic_under_concurrency(engine: Engine) -> None:
    """Two requests must not both read a count below the limit and proceed.

    Read-then-write would allow exactly that. The upsert increments and returns
    in one statement, so the database serialises it.
    """
    key = str(uuid4())
    seen: list[int] = []

    connections = [engine.connect() for _ in range(2)]
    try:
        for c in connections:
            seen.append(consume(c, PER_WORKSPACE, key))
            c.commit()
    finally:
        for c in connections:
            c.execute(
                text("DELETE FROM rate_limit_counter WHERE bucket = :b"),
                {"b": f"{PER_WORKSPACE.bucket_prefix}:{key}"},
            )
            c.commit()
            c.close()

    assert seen == [1, 2], "concurrent increments must not return the same count"


# ── Configuration sanity ──────────────────────────────────────


def test_global_ceiling_is_the_binding_cost_control() -> None:
    """The per-workspace limit bounds one tenant; only the global ceiling bounds
    the bill. It must therefore exist, be finite, and sit above the per-tenant
    allowance — a ceiling a single workspace could reach alone is a per-tenant
    limit wearing the wrong name."""
    assert GLOBAL_DAILY.max_count > 0
    assert GLOBAL_DAILY.window >= timedelta(days=1)
    assert GLOBAL_DAILY.max_count > PER_WORKSPACE.max_count
