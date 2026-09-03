"""Expiring what is time-bound.

Until Phase 2 this module's centre of gravity was Preview data, and the reason
was unusual enough to be worth remembering: **the subject of that data was not
our user.** A company whose site had been crawled by a stranger evaluating them
had no login here, could not see what we held, and could not ask an account
manager to remove it. Doc 06 §10 answered that with a short TTL and a
deletion-request path keyed on the domain rather than on an account, and this
job is what carried it out.

`doc/11` Q1 retired the unauthenticated crawl, so no third-party data is
collected and the obligation does not arise — **D9 is void rather than
satisfied.** `expire_previews` and `delete_previews_for_domain` went with
migration 0011, and the deletion path they implemented is the strongest kind:
there is nothing to delete.

What remains is time-bound data about our own users — abandoned domain claims,
and rate-limit counters for windows that have closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExpiryReport:
    rate_limit_rows_deleted: int
    claims_expired: int


async def expire_stale_claims(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Close out domain claims nobody completed.

    Marked expired rather than deleted: the attempt is part of the audit trail
    for a contested domain, and deleting it would erase who tried.
    """
    moment = now or datetime.now(UTC)
    result = await db.execute(
        text(
            "WITH stale AS ("
            "  UPDATE domain_claim SET state = 'expired'"
            "   WHERE state = 'pending' AND expires_at <= :now"
            "  RETURNING 1"
            ") SELECT count(*) FROM stale"
        ),
        {"now": moment},
    )
    return int(result.scalar_one())


async def run_expiry_sweep(db: AsyncSession, *, now: datetime | None = None) -> ExpiryReport:
    """One pass of everything time-bound. Safe to run repeatedly."""
    from app.connectors.rate_limit import purge_expired

    claims = await expire_stale_claims(db, now=now)
    counters = await purge_expired(db)
    await db.commit()

    report = ExpiryReport(counters, claims)
    if claims or counters:
        log.info("expiry.sweep", claims_expired=claims, rate_limit_rows_deleted=counters)
    return report
