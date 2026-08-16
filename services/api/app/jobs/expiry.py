"""Expiring Preview data.

Doc 07 M3's acceptance is *"no workspace exists without a verified domain, **and
Preview data expires**"*, and doc 06 §10 names the obligation precisely:

> *Crawl data for unverified domains: short TTL, and a deletion request path for
> the crawled company, which has no account.*

That last clause is the unusual part and the reason this is a job rather than a
lazy filter. **The subject of this data is not our user.** A company whose site
was crawled by a stranger evaluating them has no login here, cannot see what we
hold, and cannot ask an account manager to remove it. Retaining it past its TTL
because nothing swept it would be indefensible, so expiry is an action taken on
a schedule rather than a predicate applied at read time.

A claimed preview is exempt: once its domain is verified, the data belongs to a
workspace and falls under that workspace's retention instead.
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
    previews_deleted: int
    rate_limit_rows_deleted: int
    claims_expired: int


async def expire_previews(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Delete Preview sessions past their TTL.

    Deleted, not soft-deleted. A `deleted_at` column would leave the crawled
    company's data in the table indefinitely, which is the situation this exists
    to prevent.
    """
    moment = now or datetime.now(UTC)
    result = await db.execute(
        text(
            "WITH gone AS ("
            "  DELETE FROM preview_session"
            "   WHERE expires_at <= :now AND claimed_by_workspace_id IS NULL"
            "  RETURNING 1"
            ") SELECT count(*) FROM gone"
        ),
        {"now": moment},
    )
    return int(result.scalar_one())


async def delete_previews_for_domain(db: AsyncSession, *, domain: str) -> int:
    """The deletion-request path for a crawled company with no account.

    Doc 06 §10. Deliberately keyed on the domain rather than on an account,
    because the requester has neither — they are the subject of the data, not a
    customer.
    """
    result = await db.execute(
        text(
            "WITH gone AS ("
            "  DELETE FROM preview_session"
            "   WHERE lower(domain) = lower(:d) AND claimed_by_workspace_id IS NULL"
            "  RETURNING 1"
            ") SELECT count(*) FROM gone"
        ),
        {"d": domain},
    )
    deleted = int(result.scalar_one())
    log.info("preview.deletion_request", deleted=deleted)
    return deleted


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

    previews = await expire_previews(db, now=now)
    claims = await expire_stale_claims(db, now=now)
    counters = await purge_expired(db)
    await db.commit()

    report = ExpiryReport(previews, counters, claims)
    if previews or claims or counters:
        log.info(
            "expiry.sweep",
            previews_deleted=previews,
            claims_expired=claims,
            rate_limit_rows_deleted=counters,
        )
    return report
