"""What a research run is, and the rule that shapes all of it.

**One source failing never fails the run** (Q56). A run fans out across up to
six independent sources — a crawl, an audit, competitors, keywords, documents, a
connector — and they fail for unrelated reasons: a site is a JavaScript shell, a
connector's token expired, a competitor list was never given. Collapsing any of
those into "research failed" throws away five results that worked and tells the
founder nothing about which thing to fix.

So the run's state is **derived from its sources**, never set directly, and the
derivation has no path from one failure to a failed run. `state_for` is the
whole rule, and it is a pure function so the derivation can be argued about
without a database.

The second rule, from the same reasoning: **a source that failed must say why in
words the founder can act on.** "Failed" alone makes them retry the same thing.
`js_rendered` exists as its own outcome for exactly this — a site whose text is
behind JavaScript has not errored, and telling somebody their website is broken
when it is merely modern would be wrong twice over.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class SourceKind(StrEnum):
    """The six things a run looks at. `doc/12` P11."""

    CRAWL = "crawl"
    AUDIT = "audit"
    COMPETITORS = "competitors"
    KEYWORDS = "keywords"
    DOCUMENTS = "documents"
    CONNECTOR = "connector"


class SourceState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    SKIPPED = "skipped"
    """Nothing to do — no competitors named, no connector attached. **Not a
    failure**, and the difference is what the founder sees: a skipped source
    asks them for something, a failed one tells them we broke."""

    JS_RENDERED = "js_rendered"
    """The page's text is behind JavaScript (Q51). Its own outcome because the
    site has not errored — reporting it as failed would tell somebody their
    website is broken when it is merely modern, and the honest message is that
    we could not read it and will use their answers and documents instead."""


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


TERMINAL: Final[frozenset[SourceState]] = frozenset(
    {
        SourceState.SUCCEEDED,
        SourceState.FAILED,
        SourceState.SKIPPED,
        SourceState.JS_RENDERED,
    }
)

USABLE: Final[frozenset[SourceState]] = frozenset({SourceState.SUCCEEDED, SourceState.JS_RENDERED})
"""Outcomes that produced something. `js_rendered` is here because the crawl
still learned the site exists, its title and its links — less than a full read,
and more than nothing."""


def state_for(sources: list[SourceState]) -> RunState:
    """The run's state, derived from its sources. Never set directly.

    **There is no path here from one failed source to a failed run**, which is
    Q56 expressed as code rather than as a promise. A run fails only when it
    produced *nothing usable at all* — and even then the sources keep their own
    reasons, so the screen can say which of the six worked.

    An empty list is `queued`, not `complete`. A run with no sources has not
    finished doing nothing; it has not started.
    """
    if not sources:
        return RunState.QUEUED

    if any(s is SourceState.RUNNING for s in sources):
        return RunState.RUNNING

    if any(s not in TERMINAL for s in sources):
        return RunState.QUEUED

    # Every source has settled. The run is complete if *anything* is usable —
    # one succeeded crawl out of six sources is a run that produced something,
    # and calling it failed would discard it.
    if any(s in USABLE for s in sources):
        return RunState.COMPLETE

    # Nothing usable. Failed only if something actually broke: a run whose every
    # source was skipped had nothing to do, which is not a failure and must not
    # be reported as one to a founder who simply has no connectors yet.
    if any(s is SourceState.FAILED for s in sources):
        return RunState.FAILED

    return RunState.COMPLETE


def is_terminal(state: RunState) -> bool:
    return state in (RunState.COMPLETE, RunState.FAILED)


# How long a `running` run may go without progress before another worker may
# take it. Longer than the hard 10-minute crawl cap (D20) so a run that is
# merely slow is never stolen from a worker that is still working on it —
# reclaiming a live run would produce two workers writing the same sources.
STALE_AFTER_MINUTES: Final = 15

CLAIM_SQL: Final = """
    UPDATE research_run
       SET state = 'running', started_at = now()
     WHERE id = (
        SELECT id FROM research_run
         WHERE state = 'queued'
            OR (state = 'running' AND started_at < now() - make_interval(mins => :stale))
         ORDER BY requested_at
         FOR UPDATE SKIP LOCKED
         LIMIT 1
     )
    RETURNING id, workspace_id
"""
"""Claim exactly one run, or nothing.

**`FOR UPDATE SKIP LOCKED` is the whole mechanism.** Without `SKIP LOCKED` a
second worker blocks on the first worker's row and then claims the same run when
the lock releases; with it, the second worker steps over the locked row and
takes the next one. That is the difference between scaling the worker out and
running everything twice.

**The `OR` clause is resumability** (Q50). A worker killed mid-run leaves a row
in `running` that nothing will ever finish, and a founder watching the progress
screen would wait forever on a spinner that means nothing. After
`STALE_AFTER_MINUTES` another worker reclaims it. That window is longer than
D20's hard 10-minute cap on purpose: a run that is merely slow must never be
taken from a worker still working on it, because two workers writing the same
sources is worse than one run finishing late.

Ordered by `requested_at` — the column `research_run` actually has. It is when
the founder asked, which is also the fair order to serve them in.

Selecting and updating in one statement rather than SELECT-then-UPDATE, because
between those two statements is exactly where a second worker reads the same row.
"""


# Q55. Three manual re-runs per workspace per month, plus one weekly automatic
# crawl. The two are counted separately and deliberately: the weekly crawl is
# ours, and spending a founder's manual allowance on work they did not ask for
# would mean the product quietly consuming the budget it gave them.
MANUAL_RUNS_PER_MONTH: Final = 3
AUTOMATIC_RUNS_PER_WEEK: Final = 1


class Trigger(StrEnum):
    MANUAL = "manual"
    """A founder pressed the button. Counted against the monthly allowance."""

    AUTOMATIC = "automatic"
    """The weekly sweep. Counted against its own allowance, never theirs."""


def may_start(trigger: Trigger, *, manual_this_month: int, automatic_this_week: int) -> str | None:
    """`None` when a run may start, otherwise **why not, in words**.

    A refusal that does not say when the allowance resets is a dead end: the
    founder cannot tell whether to wait an hour or a month, so they either give
    up or ask support. Both are our failure rather than theirs.

    The counts are passed in rather than read here, so the rule stays a pure
    function — it can be argued about, and the same numbers drive both the
    refusal and the "2 of 3 left" the screen shows, which is what stops those
    two from disagreeing.
    """
    if trigger is Trigger.MANUAL:
        if manual_this_month >= MANUAL_RUNS_PER_MONTH:
            return (
                f"You have used all {MANUAL_RUNS_PER_MONTH} research runs for this "
                "month. The allowance resets at the start of next month, and the "
                "weekly automatic crawl keeps running in the meantime."
            )
        return None

    if automatic_this_week >= AUTOMATIC_RUNS_PER_WEEK:
        # Not shown to anybody — the sweep is ours. Returned as a sentence
        # anyway so the log line says what happened rather than "quota".
        return "The automatic crawl has already run this week."
    return None


def manual_runs_left(manual_this_month: int) -> int:
    """What the screen shows. Never negative: a workspace whose allowance was
    lowered mid-month should read `0 left`, not `-2`."""
    return max(0, MANUAL_RUNS_PER_MONTH - manual_this_month)
