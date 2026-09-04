"""One source failing never fails the run (Q56).

A research run fans out across six independent sources, and they fail for
unrelated reasons: a site is a JavaScript shell, a connector's token expired, a
competitor list was never given. Collapsing any of those into "research failed"
throws away the five that worked and tells the founder nothing about which thing
to fix.

The run's state is therefore **derived** from its sources rather than set, and
these tests are the derivation's specification. The property worth stating out
loud: there is no input to `state_for` where a single failure produces a failed
run while anything usable exists.
"""

from __future__ import annotations

import itertools

from app.domain.research import RunState, SourceState, state_for


def test_one_failure_among_successes_is_a_complete_run() -> None:
    """Q56, directly. Five sources worked; the run produced something."""
    assert (
        state_for(
            [
                SourceState.SUCCEEDED,
                SourceState.FAILED,
                SourceState.SUCCEEDED,
                SourceState.SKIPPED,
            ]
        )
        is RunState.COMPLETE
    )


def test_no_combination_containing_a_success_ever_fails() -> None:
    """The exhaustive version, because Q56 is a claim about *every* case.

    A single hand-picked example proves the case somebody thought of. This
    enumerates every combination of up to three sources that includes a success
    and asserts none of them fails — which is what "never" means.
    """
    for size in (1, 2, 3):
        for combination in itertools.product(SourceState, repeat=size):
            if SourceState.SUCCEEDED not in combination:
                continue
            if any(s in (SourceState.QUEUED, SourceState.RUNNING) for s in combination):
                continue
            assert state_for(list(combination)) is not RunState.FAILED, combination


def test_a_run_fails_only_when_nothing_usable_survives() -> None:
    """Failure is real and must stay reachable — a rule that can never fail is
    not a rule, it is a shape."""
    assert state_for([SourceState.FAILED]) is RunState.FAILED
    assert state_for([SourceState.FAILED, SourceState.FAILED]) is RunState.FAILED


def test_every_source_skipped_is_complete_not_failed() -> None:
    """A run with nothing to do had nothing to do.

    Reporting it as failed would tell a founder with no connectors and no named
    competitors that our research broke, when in fact we asked them for nothing
    and they gave us nothing.
    """
    assert state_for([SourceState.SKIPPED, SourceState.SKIPPED]) is RunState.COMPLETE


def test_a_javascript_shell_is_usable_and_not_a_failure() -> None:
    """Q51. A site whose text is behind JavaScript has not errored.

    The crawl still learned the site exists, its title and its links — less than
    a full read and more than nothing. Reporting it as failed would tell
    somebody their website is broken when it is merely modern.
    """
    assert state_for([SourceState.JS_RENDERED]) is RunState.COMPLETE
    assert state_for([SourceState.JS_RENDERED, SourceState.FAILED]) is RunState.COMPLETE


def test_a_run_is_running_while_any_source_is() -> None:
    assert state_for([SourceState.SUCCEEDED, SourceState.RUNNING]) is RunState.RUNNING


def test_an_unstarted_source_keeps_the_run_out_of_a_terminal_state() -> None:
    """A run that reported `complete` with a source still queued would show a
    founder a finished screen and then change under them."""
    assert state_for([SourceState.SUCCEEDED, SourceState.QUEUED]) is RunState.QUEUED


def test_a_run_with_no_sources_has_not_finished_doing_nothing() -> None:
    """Empty is `queued`, not `complete`. The alternative reports a run that
    never started as one that succeeded."""
    assert state_for([]) is RunState.QUEUED
