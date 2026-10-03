"""Three manual runs a month, one automatic crawl a week (Q55).

The rule is small; the two properties it has to keep are not obvious.

**The weekly crawl never spends the founder's allowance.** It is our sweep, run
because we decided to, and charging it to the three they were promised would
mean the product quietly consuming the budget it gave them.

**A refusal says when the allowance returns.** "Quota exceeded" leaves somebody
unable to tell whether to wait an hour or a month, so they give up or ask
support — both our failure rather than theirs.
"""

from __future__ import annotations

from app.domain.research import (
    AUTOMATIC_RUNS_PER_WEEK,
    MANUAL_RUNS_PER_MONTH,
    Trigger,
    manual_runs_left,
    may_start,
)


def test_the_numbers_are_what_the_spec_says() -> None:
    assert MANUAL_RUNS_PER_MONTH == 3
    assert AUTOMATIC_RUNS_PER_WEEK == 1


def test_a_founder_gets_three_and_then_a_reason() -> None:
    for used in range(MANUAL_RUNS_PER_MONTH):
        assert may_start(Trigger.MANUAL, manual_this_month=used, automatic_this_week=0) is None

    refusal = may_start(
        Trigger.MANUAL, manual_this_month=MANUAL_RUNS_PER_MONTH, automatic_this_week=0
    )
    assert refusal is not None
    assert "next month" in refusal, "a refusal must say when the allowance returns"


def test_the_weekly_crawl_never_spends_the_manual_allowance() -> None:
    """The property most easily lost by counting runs in one place.

    A founder who has used all three must still get their automatic crawl — and
    an automatic crawl that has run must not stop them starting a manual one.
    """
    assert (
        may_start(
            Trigger.AUTOMATIC,
            manual_this_month=MANUAL_RUNS_PER_MONTH,
            automatic_this_week=0,
        )
        is None
    )
    assert may_start(Trigger.MANUAL, manual_this_month=0, automatic_this_week=1) is None


def test_the_automatic_crawl_runs_once_a_week() -> None:
    assert may_start(Trigger.AUTOMATIC, manual_this_month=0, automatic_this_week=0) is None
    assert may_start(Trigger.AUTOMATIC, manual_this_month=0, automatic_this_week=1) is not None


def test_the_remaining_count_never_goes_negative() -> None:
    """A workspace whose allowance was lowered mid-month should read `0 left`,
    not `-2`. The screen shows this number directly."""
    assert manual_runs_left(0) == MANUAL_RUNS_PER_MONTH
    assert manual_runs_left(MANUAL_RUNS_PER_MONTH) == 0
    assert manual_runs_left(MANUAL_RUNS_PER_MONTH + 5) == 0


def test_the_refusal_and_the_count_agree() -> None:
    """The same numbers drive both, which is what stops the screen saying
    "1 left" beside a button that refuses."""
    for used in range(MANUAL_RUNS_PER_MONTH + 3):
        refused = may_start(Trigger.MANUAL, manual_this_month=used, automatic_this_week=0)
        assert (refused is None) == (manual_runs_left(used) > 0), used
