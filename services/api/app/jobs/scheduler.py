"""Scheduled work.

Deliberately minimal. Doc 07 §3 calls for "a scheduler for crawls, refreshes,
score recomputation and briefs"; today there is exactly one job, and adding a
queue, a broker and a worker pool for it would be building for a load that does
not exist.

APScheduler in-process is the honest choice at this size, and it has one
limitation worth naming rather than discovering: **with more than one API
process, every process runs the job.** The expiry sweep is idempotent so that is
currently harmless, but the moment a job is *not* idempotent — sending a brief,
charging a card — this needs a real scheduler with leader election. That is
recorded here so it is a decision rather than an accident.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import _unscoped_session
from app.jobs.expiry import run_expiry_sweep
from app.logging import get_logger

log = get_logger(__name__)

EXPIRY_INTERVAL_MINUTES = 60


async def _expiry_job() -> None:
    try:
        async with _unscoped_session() as db:
            await run_expiry_sweep(db)
    except Exception as exc:
        log.warning("expiry.sweep.failed", error=type(exc).__name__)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _expiry_job,
        trigger=IntervalTrigger(minutes=EXPIRY_INTERVAL_MINUTES),
        id="expiry_sweep",
        name="Expire Preview data and stale claims",
        # Skip rather than pile up if a run overruns its window.
        max_instances=1,
        coalesce=True,
        # Run shortly after start so a long-lived process is not the only thing
        # standing between expired data and its deletion.
        next_run_time=None,
    )
    return scheduler
