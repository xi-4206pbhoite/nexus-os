"""Repeat Preview requests, and what the rate limiter tells a visitor.

Two behaviours, both fixes for the same complaint: the landing page's only action
returned "Too many analyses right now. Please try again later" to ordinary use.

- **A repeated domain is served from storage.** No crawl happens, so it must not
  be charged against the crawl budget. Before this, a reload — or a second person
  in the same office, sharing one NAT address — spent a slot, and three people
  looking at the same company exhausted the per-domain limit for a day.
- **A 429 says how long to wait.** `Retry-After` was set by the API and dropped
  by the proxy in front of it, leaving the visitor with "later".

The TTL assertions belong here too: caching and retention are the same mechanism
read from two directions, and a cache that outlived the TTL would quietly extend
how long we hold an audit of a company that has no account with us.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine, text

from app.config import Settings, get_settings
from app.connectors.rate_limit import GLOBAL_DAILY, PER_DOMAIN, PER_IP, RateLimitedError
from app.db import get_engine, get_sessionmaker
from app.routes.preview import PreviewOut, _fresh_preview_for, _humanise_wait, _too_many
from tests.dburl import async_database_url, database_url

DB_URL = database_url()
ASYNC_DB_URL = async_database_url()
# The real marker, declared in pyproject.toml. Previously a local
# `pytest.mark.skipif` — nine copies of it, so nine places a database suite
# could silently vanish from a green run. The skip decision now lives in
# conftest.py, which fails the session if it ever fires.
requires_db = pytest.mark.requires_db


# ── The 429 a person actually reads ───────────────────────────


def test_retry_after_is_set_on_the_response() -> None:
    """The header is the machine-readable half. Nothing can count down without it."""
    exc = _too_many(RateLimitedError("ip", retry_after_seconds=1800))

    assert exc.status_code == 429
    assert exc.headers is not None
    assert exc.headers["Retry-After"] == "1800"


def test_the_message_states_a_duration_rather_than_later() -> None:
    """A bare "later" is not actionable: it could mean thirty seconds or a day."""
    detail = str(_too_many(RateLimitedError("ip", retry_after_seconds=1800)).detail)

    assert "30 minutes" in detail
    assert "later" not in detail.lower()


def test_the_message_does_not_disclose_which_limit_was_hit() -> None:
    """Which bucket is exhausted is our business. Telling a caller lets them
    work out whether to change address or change target."""
    for scope in ("ip", "domain", "global"):
        detail = str(_too_many(RateLimitedError(scope, retry_after_seconds=60)).detail)
        assert scope not in detail.lower()


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (1, "in under a minute"),
        (45, "in under a minute"),
        (300, "in about 5 minutes"),
        (1800, "in about 30 minutes"),
        (3600, "in about an hour"),
        (7200, "in about 2 hours"),
        (86_400, "in about 24 hours"),
    ],
)
def test_waits_are_phrased_in_units_a_person_uses(seconds: int, expected: str) -> None:
    assert _humanise_wait(seconds) == expected


# ── Retention ─────────────────────────────────────────────────


def test_the_preview_ttl_is_short() -> None:
    """Doc 06 §1.1 requires a short TTL, and the subject of this data is a company
    that has no account here and never consented to being crawled. A week was not
    short; it was the default nobody revisited."""
    assert Settings().preview_ttl_hours <= 24


# ── Budgets ───────────────────────────────────────────────────


def test_the_per_ip_allowance_survives_a_shared_address() -> None:
    """An office, a university or any carrier NAT is one address for many people,
    and with no trusted proxy configured every visitor lands in one bucket. The
    allowance has to leave room for that or the limiter rejects customers."""
    assert PER_IP.max_count >= 15
    assert PER_IP.window <= timedelta(hours=1)


def test_the_global_ceiling_is_still_the_binding_cost_control() -> None:
    """Loosening the per-key limits must not raise the maximum spend. Only this
    limit bounds the bill, so it stays the tightest of the three."""
    assert GLOBAL_DAILY.max_count > 0
    assert GLOBAL_DAILY.max_count > PER_IP.max_count
    assert GLOBAL_DAILY.max_count > PER_DOMAIN.max_count


def test_the_per_domain_limit_still_stops_a_reflected_dos() -> None:
    """Caching answers repeats, so this limit now counts *fresh crawls of one
    target* — which is the abuse it existed to stop. It must stay small."""
    assert PER_DOMAIN.max_count <= 10
    assert PER_DOMAIN.window >= timedelta(hours=1)


# ── The cache itself, against the real database ───────────────


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
    """Committed rather than rolled back: `_fresh_preview_for` reads on its own
    connection, so an uncommitted row would be invisible to it. Cleaned up by
    domain, which is unique per test."""
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Point application settings at the real database for this test.

    `conftest` pins the URL to empty so that no test depends on machine state by
    accident, so opting back in has to be explicit — and has to use the asyncpg
    spelling, because this exercises `app/` code on the app's own driver rather
    than asserting database behaviour over psycopg2.

    The engine is disposed on the way out. A cached engine holding connections
    into the next test is how an async suite starts failing in ways that depend
    on test order.
    """
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


def audit_json(domain: str) -> str:
    """A stored audit in the shape the route writes."""
    return json.dumps(
        {
            "preview_id": str(UUID(int=0)),
            "domain": domain,
            "final_url": f"https://{domain}/",
            "overall": 69,
            "scored_categories": 3,
            "categories": [
                {
                    "category": "brand",
                    "score": 55,
                    "max_score": 70,
                    "percentage": 79,
                    "checks": [
                        {
                            "id": "brand.title",
                            "label": "Page title present",
                            "passed": True,
                            "evidence": "Title: 'Acme'",
                        }
                    ],
                }
            ],
            "locked": [],
            "expires_at": datetime.now(UTC).isoformat(),
            "truncated": False,
        }
    )


def insert_preview(
    conn: Connection,
    domain: str,
    *,
    status: str = "complete",
    expires_in: timedelta = timedelta(hours=12),
    claimed: bool = False,
    with_audit: bool = True,
    created_offset: timedelta = timedelta(0),
) -> UUID:
    row = conn.execute(
        text(
            "INSERT INTO preview_session"
            " (domain, requested_url, status, audit_json, expires_at,"
            "  claimed_by_workspace_id, created_at)"
            " VALUES (:d, :u, :s, CAST(:a AS jsonb), :exp, :claimed, now() + :off)"
            " RETURNING id"
        ),
        {
            "d": domain,
            "u": f"https://{domain}/",
            "s": status,
            "a": audit_json(domain) if with_audit else None,
            "exp": datetime.now(UTC) + expires_in,
            "claimed": uuid4() if claimed else None,
            "off": created_offset,
        },
    )
    preview_id = UUID(str(row.scalar_one()))
    conn.commit()
    return preview_id


def cleanup(conn: Connection, domain: str) -> None:
    conn.execute(text("DELETE FROM preview_session WHERE domain = :d"), {"d": domain})
    conn.commit()


@requires_db
async def test_a_fresh_audit_is_returned_without_a_crawl(conn: Connection, app_db: None) -> None:
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        preview_id = insert_preview(conn, domain)
        found = await _fresh_preview_for(domain)

        assert found is not None
        assert found.preview_id == preview_id
        assert found.domain == domain
        assert found.overall == 69
        assert found.scored_categories == 3
    finally:
        cleanup(conn, domain)


@requires_db
async def test_the_locked_categories_are_reasserted_on_a_cache_hit(
    conn: Connection, app_db: None
) -> None:
    """`locked` is not persisted with the audit — it describes what the product
    can offer, not what was observed. A cache hit must still carry it, or a
    returning visitor sees a score with no explanation of the missing seven."""
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        insert_preview(conn, domain)
        found = await _fresh_preview_for(domain)

        assert found is not None
        assert len(found.locked) == 7
        assert all(item.unlock for item in found.locked), "every locked tile names its unlock"
        assert found.scored_categories + len(found.locked) == 10
    finally:
        cleanup(conn, domain)


@requires_db
async def test_an_expired_audit_is_not_served(conn: Connection, app_db: None) -> None:
    """The TTL is a retention promise, so it has to bind reads as well as the
    sweep. Serving an expired row would keep a third party's audit alive for as
    long as anyone kept asking."""
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        insert_preview(conn, domain, expires_in=timedelta(hours=-1))
        assert await _fresh_preview_for(domain) is None
    finally:
        cleanup(conn, domain)


@requires_db
async def test_a_claimed_audit_is_not_served_to_an_anonymous_visitor(
    conn: Connection, app_db: None
) -> None:
    """Once claimed, the row belongs to a workspace. Handing it back on the
    unauthenticated path would leak whatever that workspace has since done with
    it."""
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        insert_preview(conn, domain, claimed=True)
        assert await _fresh_preview_for(domain) is None
    finally:
        cleanup(conn, domain)


@requires_db
@pytest.mark.parametrize("status", ["failed", "blocked", "pending", "running"])
async def test_only_a_completed_audit_is_served(
    status: str, conn: Connection, app_db: None
) -> None:
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        insert_preview(conn, domain, status=status)
        assert await _fresh_preview_for(domain) is None
    finally:
        cleanup(conn, domain)


@requires_db
async def test_a_row_without_an_audit_is_not_served(conn: Connection, app_db: None) -> None:
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        insert_preview(conn, domain, with_audit=False)
        assert await _fresh_preview_for(domain) is None
    finally:
        cleanup(conn, domain)


@requires_db
async def test_the_most_recent_audit_wins(conn: Connection, app_db: None) -> None:
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        insert_preview(conn, domain, created_offset=timedelta(hours=-2))
        newest = insert_preview(conn, domain)

        found = await _fresh_preview_for(domain)
        assert found is not None
        assert found.preview_id == newest
    finally:
        cleanup(conn, domain)


@requires_db
async def test_the_lookup_is_case_insensitive(conn: Connection, app_db: None) -> None:
    """Hostnames are case-insensitive, so `ACME.OM` and `acme.om` are one target.
    Treating them as two would let a trivial change of case bypass the per-domain
    limit as well as the cache."""
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        insert_preview(conn, domain.upper())
        assert await _fresh_preview_for(domain) is not None
    finally:
        conn.execute(text("DELETE FROM preview_session WHERE lower(domain) = :d"), {"d": domain})
        conn.commit()


@requires_db
async def test_an_unreadable_stored_audit_falls_back_to_a_recrawl(
    conn: Connection, app_db: None
) -> None:
    """An audit written by an older shape of the model must not be guessed at.
    Returning None means "crawl again", which is correct and cheap; coercing it
    would put invented structure in front of a user."""
    domain = f"cache-{uuid4().hex[:8]}.example"
    try:
        conn.execute(
            text(
                "INSERT INTO preview_session"
                " (domain, requested_url, status, audit_json, expires_at)"
                " VALUES (:d, :u, 'complete', CAST(:a AS jsonb), :exp)"
            ),
            {
                "d": domain,
                "u": f"https://{domain}/",
                "a": json.dumps({"unexpected": "shape"}),
                "exp": datetime.now(UTC) + timedelta(hours=12),
            },
        )
        conn.commit()

        assert await _fresh_preview_for(domain) is None
    finally:
        cleanup(conn, domain)


@requires_db
async def test_an_unknown_domain_has_no_cache_entry(app_db: None) -> None:
    assert await _fresh_preview_for(f"never-seen-{uuid4().hex}.example") is None


def test_audit_json_fixture_matches_the_response_model() -> None:
    """Guards the tests above from passing vacuously: if `PreviewOut` changes
    shape, the fixture must fail here rather than silently exercising the
    unreadable-audit path everywhere."""
    parsed: dict[str, Any] = json.loads(audit_json("acme.example"))
    assert PreviewOut.model_validate(parsed).domain == "acme.example"
