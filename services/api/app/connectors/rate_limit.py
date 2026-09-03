"""Rate limiting the research path.

Doc 06 §1.2: *"Metered APIs must never sit on an unauthenticated path... Without
this, a script exhausts a paid quota and degrades the product for paying
tenants."*

Until Phase 2 that unauthenticated path existed, and the limits were shaped
around it: **per IP**, to stop one client hammering the endpoint; **per domain**,
to stop many clients being pointed at one victim; and a **global daily ceiling**
to bound the bill. `doc/11` Q1 retired the anonymous audit, and both of the first
two lost their subject with it. There is no address to attribute a crawl to when
every caller is authenticated, and no reflected-DoS shape to block when the
target has to be a domain the workspace has claimed.

What replaces them is the identity that now exists on every call:

- **per workspace** — the tenant fairness limit. One customer running research in
  a loop must not consume the day's budget that the others are paying for.
- **global daily ceiling** — the actual cost containment, unchanged. The first
  limit bounds any single tenant; only this one bounds the bill.

Counters are fixed-window and live in Postgres (ADR 0001 — no Redis). A fixed
window permits up to 2x the limit across a boundary; that is an accepted
trade-off for a ceiling whose purpose is bounding spend rather than precision.

The re-keying needed no migration. A bucket is an opaque string, so the old
`ip:` and `domain:` rows are simply never written again and age out through
`purge_expired`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class Limit:
    bucket_prefix: str
    max_count: int
    window: timedelta


# Two constraints set these numbers, and neither is "how much crawling feels
# reasonable":
#
# - **Only the global ceiling bounds the bill.** Loosening the per-workspace
#   limit does not raise the maximum spend, because `GLOBAL_DAILY` still caps
#   the crawls per day across every tenant. That is the limit to keep tight.
# - **The per-workspace limit is about fairness, not cost.** It exists so one
#   customer looping on research cannot spend the ceiling the others are paying
#   for. Set too tight it rejects ordinary use, which is the failure that costs
#   a customer rather than money.
#
# `PER_WORKSPACE` is deliberately generous against `GLOBAL_DAILY`: a single
# tenant can take a tenth of the day's budget before being told to wait, and
# ten busy tenants can coexist without any of them noticing a limit exists.
#
# **P11 owns the real number.** It builds the research job model and will know
# what one run actually costs; until then this bounds a path with no callers,
# and a limit nobody has measured should not pretend otherwise.
PER_WORKSPACE = Limit("workspace", max_count=50, window=timedelta(hours=24))
GLOBAL_DAILY = Limit("global", max_count=500, window=timedelta(days=1))


class RateLimitedError(Exception):
    def __init__(self, scope: str, retry_after_seconds: int) -> None:
        super().__init__(f"rate limited: {scope}")
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


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
