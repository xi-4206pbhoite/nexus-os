"""Rate limiting for the unauthenticated Preview path.

Doc 06 §1.2: *"Metered APIs must never sit on an unauthenticated path... Without
this, a script exhausts a paid quota and degrades the product for paying
tenants."*

Three independent limits, all of which must pass:

- **per IP** — stops one client hammering the endpoint
- **per domain** — stops many clients being pointed at one victim, which is
  also what keeps this from being used as a reflected DoS against a third party
- **global daily ceiling** — the actual cost containment. The first two limit
  any single abuser; only this one bounds the bill.

Counters are fixed-window and live in Postgres (ADR 0001 — no Redis). A fixed
window permits up to 2x the limit across a boundary; that is an accepted
trade-off for a ceiling whose purpose is bounding spend rather than precision.

The IP is stored **hashed**. It is needed for limiting and abuse response, not
for identifying people, and the unauthenticated path should not accumulate a
plaintext log of who looked at what.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class Limit:
    bucket_prefix: str
    max_count: int
    window: timedelta


# Sized for the failure mode that actually costs money, which is not a curious
# visitor. Two constraints pulled these numbers:
#
# - **A bucket is shared more often than it looks.** An office, a university or
#   any carrier NAT presents one address for many people, and with no trusted
#   proxy configured (see `client_ip`) every visitor collapses into a single
#   bucket. At 5/hour two colleagues could lock each other out of the landing
#   page, so the per-IP limit was rejecting customers, not scripts.
# - **Only the global ceiling bounds the bill.** Loosening the per-key limits
#   does not raise the maximum spend, because `GLOBAL_DAILY` still caps the
#   number of crawls per day. That is the limit to keep tight.
#
# A repeated domain inside its TTL is served from `preview_session` without a
# crawl and without consuming any of these — so the per-domain limit counts
# *fresh crawls of one target*, which is the reflected-DoS shape it exists to
# stop, rather than page reloads.
PER_IP = Limit("ip", max_count=20, window=timedelta(hours=1))
PER_DOMAIN = Limit("domain", max_count=5, window=timedelta(hours=24))
GLOBAL_DAILY = Limit("global", max_count=500, window=timedelta(days=1))


class RateLimitedError(Exception):
    def __init__(self, scope: str, retry_after_seconds: int) -> None:
        super().__init__(f"rate limited: {scope}")
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


def hash_ip(ip: str, *, secret: str) -> str:
    """Keyed hash, so the table is not a rainbow-table lookup of visitor IPs."""
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()


def _window_start(now: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)


async def check_and_increment(
    db: AsyncSession, limit: Limit, key: str, *, now: datetime | None = None
) -> None:
    """Consume one unit against a bucket, or raise `RateLimited`.

    The upsert increments and returns the new count in a single statement, so
    two concurrent requests cannot both read a count below the limit and both
    proceed.
    """
    moment = now or datetime.now(UTC)
    start = _window_start(moment, limit.window)
    bucket = f"{limit.bucket_prefix}:{key}"

    result = await db.execute(
        text(
            """
            INSERT INTO rate_limit_counter (bucket, window_start, count)
            VALUES (:bucket, :start, 1)
            ON CONFLICT (bucket, window_start)
            DO UPDATE SET count = rate_limit_counter.count + 1
            RETURNING count
            """
        ),
        {"bucket": bucket, "start": start},
    )
    count = int(result.scalar_one())

    if count > limit.max_count:
        elapsed = (moment - start).total_seconds()
        retry_after = max(1, int(limit.window.total_seconds() - elapsed))
        raise RateLimitedError(limit.bucket_prefix, retry_after)


async def purge_expired(db: AsyncSession, *, older_than: datetime | None = None) -> int:
    """Drop counter rows for windows that can no longer be current."""
    cutoff = older_than or (datetime.now(UTC) - timedelta(days=2))
    result = await db.execute(
        text(
            "WITH deleted AS ("
            "  DELETE FROM rate_limit_counter WHERE window_start < :cutoff RETURNING 1"
            ") SELECT count(*) FROM deleted"
        ),
        {"cutoff": cutoff},
    )
    return int(result.scalar_one())
