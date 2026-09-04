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
