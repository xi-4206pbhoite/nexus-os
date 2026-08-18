"""The scheduler, which had no tests and therefore shipped permanently paused.

`build_scheduler` passed `next_run_time=None`, which is not "no opinion" — it is
APScheduler's representation of *paused*. `add_job` computes a first fire time
only when the attribute is absent; setting it to None means one is never
computed, so the job never ran in any deployment for the life of the module.

Nothing caught it because nothing tested it, and because startup logged
`scheduler.started jobs=['expiry_sweep']` throughout. That log confirmed the job
was *registered*, which was true, and said nothing about whether it would fire.

What it cost: `jobs/expiry.py` calls the Preview TTL an obligation to a company
that has no account here and never consented to being crawled. That data was
retained indefinitely. `rate_limit_counter` grew without bound on the
unauthenticated path.

The first test below is four lines and would have caught all of it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.jobs.scheduler import EXPIRY_INTERVAL_MINUTES, FIRST_RUN_DELAY, build_scheduler


def test_every_job_has_a_fire_time() -> None:
    """The regression. `next_run_time is None` means paused, not unscheduled."""
    jobs = build_scheduler().get_jobs()

    assert jobs, "no jobs registered at all"
    for job in jobs:
        assert job.next_run_time is not None, (
            f"job {job.id!r} is paused and will never fire — "
            "this is what `next_run_time=None` means to APScheduler"
        )


def test_the_expiry_sweep_is_registered() -> None:
    assert "expiry_sweep" in {job.id for job in build_scheduler().get_jobs()}


def test_the_embedding_pass_is_registered() -> None:
    """Task 5.6. A pass nothing triggers leaves every uploaded document
    permanently unsearchable, with no error anywhere to say so."""
    assert "embedding_pass" in {job.id for job in build_scheduler().get_jobs()}


def test_the_first_run_is_soon_after_start_not_a_whole_interval_away() -> None:
    """The module promises "shortly after start", and it matters.

    A service that restarts daily would otherwise never sweep: each restart
    pushes the first run a full interval out, and the process may not live that
    long.
    """
    job = next(j for j in build_scheduler().get_jobs() if j.id == "expiry_sweep")
    assert job.next_run_time is not None

    delay = job.next_run_time - datetime.now(UTC)
    assert delay <= FIRST_RUN_DELAY + timedelta(seconds=5)
    assert delay < timedelta(minutes=EXPIRY_INTERVAL_MINUTES), (
        "the first run must not be a whole interval away"
    )


def test_a_slow_run_is_skipped_rather_than_stacked() -> None:
    """Without both flags, a sweep overrunning its window would start a second
    copy against the same rows, and a paused process would fire every missed run
    at once on resume."""
    job = next(j for j in build_scheduler().get_jobs() if j.id == "expiry_sweep")

    assert job.max_instances == 1
    assert job.coalesce is True


def test_the_interval_is_finite_and_reasonable() -> None:
    """The sweep is the only thing enforcing the Preview TTL, so its cadence is
    the real retention granularity — whatever the TTL says."""
    assert 0 < EXPIRY_INTERVAL_MINUTES <= 24 * 60
