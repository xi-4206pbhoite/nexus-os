"""A session extends on activity, and only on activity.

`doc/11` §5.2: twelve hours, with a rolling refresh. Twelve hours alone is the
wrong shape for both parties — someone working a long day is signed out mid-task,
and a session that never moves is a fixed window an attacker can wait out.

Three properties, and the second is the one that makes this affordable:

1. **Activity extends the window.** Any resolved request, not just login.
2. **Not every request writes.** The extension happens only once the window is
   more than half spent. A refresh on every request turns every authenticated
   read into a write, which on a serverless Postgres billed by the statement is
   a cost bug wearing a security feature's clothes.
3. **A dead session is never resurrected.** Expired and revoked sessions are
   absent from the lookup, so there is nothing to extend — asserted, because the
   obvious implementation (`UPDATE ... SET expires_at` then re-read) would
   happily revive a session that had just been revoked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db
TTL = 12 * 60 * 60


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def _seed(db: object, *, expires_in: timedelta) -> tuple[str, object]:
    """A user and a session whose expiry we control."""
    from app.auth.tokens import hash_token, new_token

    user = uuid4()
    token = new_token()
    await db.execute(  # type: ignore[attr-defined]
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"sess-{user.hex[:8]}@example.com"},
    )
    await db.execute(  # type: ignore[attr-defined]
        sa.text("INSERT INTO user_session (user_id, token_hash, expires_at) VALUES (:u, :h, :x)"),
        {"u": str(user), "h": hash_token(token), "x": datetime.now(UTC) + expires_in},
    )
    await db.commit()  # type: ignore[attr-defined]
    return token, user


async def _expiry_of(db: object, token: str) -> datetime | None:
    from app.auth.tokens import hash_token

    return (  # type: ignore[no-any-return]
        await db.execute(  # type: ignore[attr-defined]
            sa.text("SELECT expires_at FROM user_session WHERE token_hash = :h"),
            {"h": hash_token(token)},
        )
    ).scalar()


async def _cleanup(db: object, user: object) -> None:
    await db.execute(  # type: ignore[attr-defined]
        sa.text("DELETE FROM user_session WHERE user_id = :u"), {"u": str(user)}
    )
    await db.execute(  # type: ignore[attr-defined]
        sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)}
    )
    await db.commit()  # type: ignore[attr-defined]


@requires_db
async def test_a_session_well_into_its_window_is_extended(app_db: None) -> None:
    from app.auth.service import resolve_session
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        # One hour left of twelve: well past the halfway mark.
        token, user = await _seed(db, expires_in=timedelta(hours=1))
        try:
            before = await _expiry_of(db, token)
            assert await resolve_session(db, token=token) is not None
            await db.commit()
            after = await _expiry_of(db, token)

            assert before is not None and after is not None
            assert after > before, "activity did not extend the session"
            # Extended to a fresh full window, not merely nudged.
            assert after > datetime.now(UTC) + timedelta(hours=11)
        finally:
            await _cleanup(db, user)


@requires_db
async def test_a_fresh_session_is_not_rewritten_on_every_request(app_db: None) -> None:
    """The affordability property. A refresh per request makes every
    authenticated read a write."""
    from app.auth.service import resolve_session
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        # Almost the whole window left — nothing to gain by extending.
        token, user = await _seed(db, expires_in=timedelta(hours=11, minutes=59))
        try:
            before = await _expiry_of(db, token)
            assert await resolve_session(db, token=token) is not None
            await db.commit()
            after = await _expiry_of(db, token)

            assert before == after, "a fresh session was rewritten for no benefit"
        finally:
            await _cleanup(db, user)


@requires_db
async def test_an_expired_session_is_not_revived(app_db: None) -> None:
    """The one that would be easy to get wrong. An `UPDATE ... SET expires_at`
    that forgot its own `WHERE expires_at > now()` would resurrect exactly the
    sessions the expiry exists to end."""
    from app.auth.service import resolve_session
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        token, user = await _seed(db, expires_in=timedelta(hours=-1))
        try:
            before = await _expiry_of(db, token)
            assert await resolve_session(db, token=token) is None
            await db.commit()
            after = await _expiry_of(db, token)

            assert before == after, "an expired session had its window extended"
        finally:
            await _cleanup(db, user)


@requires_db
async def test_a_revoked_session_is_not_revived(app_db: None) -> None:
    """Logout, a password reset, and an administrator ending a session all work
    by revoking. Extending one would undo every one of them."""
    from app.auth.service import resolve_session
    from app.auth.tokens import hash_token
    from app.db import _unscoped_session

    async with _unscoped_session() as db:
        token, user = await _seed(db, expires_in=timedelta(hours=1))
        try:
            await db.execute(
                sa.text("UPDATE user_session SET revoked_at = now() WHERE token_hash = :h"),
                {"h": hash_token(token)},
            )
            await db.commit()

            before = await _expiry_of(db, token)
            assert await resolve_session(db, token=token) is None
            await db.commit()
            assert await _expiry_of(db, token) == before
        finally:
            await _cleanup(db, user)
