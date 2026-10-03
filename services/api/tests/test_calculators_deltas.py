"""Deltas, weighting, exposure and composite scoring — boundaries and zero.

`doc/12` P14 asks for boundary and zero-delta tests on each. The reason is one
rule applied four times: **a number that cannot be computed must be named, not
substituted.** The substitute is always plausible, always wrong, and always
looks like a measurement.
"""

from __future__ import annotations

from app.calculators.deltas import Absent, composite, delta, exposure, weighted


def test_a_zero_baseline_is_not_zero_percent() -> None:
    """The clearest case of the whole phase.

    Dividing by zero is undefined; reporting 0% claims nothing moved, when in
    fact there was nothing to move from. A founder seeing "0%" beside their
    first month of revenue would reasonably conclude the product is broken.
    """
    result = delta(current=5000.0, previous=0.0)
    assert result.percent is None
    assert result.absent is Absent.NO_BASELINE


def test_an_actual_zero_delta_is_unchanged_not_absent() -> None:
    """The other half. Nothing moved *is* a measurement, and it must survive as
    one — the caller renders "unchanged" rather than "0%"."""
    result = delta(current=100.0, previous=100.0)
    assert result.percent == 0.0
    assert result.unchanged
    assert result.absent is None


def test_a_negative_baseline_does_not_flip_the_sign() -> None:
    """Dividing by a negative previous value inverts the direction: a loss
    shrinking would read as a fall. `abs()` on the denominator keeps "smaller
    loss" reading as an improvement."""
    improving = delta(current=-50.0, previous=-100.0)
    assert improving.percent is not None and improving.percent > 0


def test_a_missing_input_is_skipped_not_scored_zero() -> None:
    """A department that reports nothing has not scored zero. Treating it that
    way drags the composite down and makes an absence look like a failure."""
    both = weighted({"a": 80.0, "b": 60.0}, {"a": 1.0, "b": 1.0})
    only_a = weighted({"a": 80.0}, {"a": 1.0, "b": 1.0})

    assert both == 70.0
    assert only_a == 80.0, "b is absent, not zero"


def test_weighting_with_nothing_in_common_is_named() -> None:
    assert weighted({"a": 1.0}, {"b": 1.0}) is Absent.NO_DATA
    assert weighted({}, {}) is Absent.NO_DATA


def test_zero_weights_do_not_divide_by_zero() -> None:
    assert weighted({"a": 5.0}, {"a": 0.0}) is Absent.NO_DATA


def test_exposure_against_an_empty_total_is_named() -> None:
    """ "100%" when the total is zero would be a confident statement about a
    company that has no suppliers."""
    assert exposure(amount=5.0, total=0.0) is Absent.NO_BASELINE
    assert exposure(amount=25.0, total=100.0) == 25.0


def test_a_composite_is_clamped_at_both_ends() -> None:
    """A composite reading 104 tells a founder the number is made up, and they
    would be right."""
    assert composite({"a": 150.0}, {"a": 1.0}) == 100.0
    assert composite({"a": -20.0}, {"a": 1.0}) == 0.0


def test_a_composite_with_no_inputs_is_named_not_zero() -> None:
    """Zero is a terrible score. No data is not a score at all, and a dashboard
    showing 0 out of 100 for a company that simply has not connected anything is
    making a statement about their business (I10)."""
    assert composite({}, {"a": 1.0}) is Absent.NO_DATA
