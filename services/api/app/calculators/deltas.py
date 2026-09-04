"""Deltas, weighting, exposure and composite scoring. All pure, all boundary-safe.

`doc/12` P14. Every function here returns a **number or a named absence**, never
a plausible substitute — because the substitute is the failure. A delta computed
against zero is the clearest case: the arithmetic says infinity, the honest
answer is "there was nothing to compare against", and the tempting answer is 0%,
which reads as "nothing changed" and is a different claim entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Absent(StrEnum):
    """Why a number could not be computed. Rendered, never silently skipped."""

    NO_BASELINE = "no_baseline"
    """The previous period was zero or missing. **Not 0%** — "we have nothing to
    compare against" and "nothing changed" are different statements, and only
    one of them is true."""

    NO_DATA = "no_data"
    """Nothing to compute from at all."""

    NOT_APPLICABLE = "not_applicable"
    """The calculation does not apply to this business — a company with no
    inventory has no stock turnover, and rendering 0 would look like a very bad
    stock turnover."""


@dataclass(frozen=True, slots=True)
class Delta:
    """A change, or the reason there isn't one."""

    percent: float | None = None
    absent: Absent | None = None

    @property
    def unchanged(self) -> bool:
        """Exactly zero. The caller renders "unchanged" rather than "0%" —
        technically the same and read completely differently."""
        return self.percent == 0.0


def delta(current: float, previous: float) -> Delta:
    """Percentage change, or a named absence.

    **Zero baseline is not zero percent.** Dividing by it is undefined and
    reporting 0% claims nothing moved, when in fact there was nothing to move
    from. A founder seeing "0%" beside their first month of revenue would
    reasonably conclude the product is broken.
    """
    if previous == 0:
        return Delta(absent=Absent.NO_BASELINE)
    return Delta(percent=((current - previous) / abs(previous)) * 100.0)


def weighted(values: dict[str, float], weights: dict[str, float]) -> float | Absent:
    """A weighted average over the keys present in **both**.

    Missing keys are skipped and the weights renormalised, rather than treated
    as zero. A department that reports nothing has not scored zero — treating it
    that way drags a composite down and makes an absence look like a failure.
    """
    shared = {k: weights[k] for k in values if k in weights and weights[k] > 0}
    total = sum(shared.values())
    if not shared or total == 0:
        return Absent.NO_DATA
    return sum(values[k] * w for k, w in shared.items()) / total


def exposure(amount: float, total: float) -> float | Absent:
    """One part's share of a whole, as a percentage.

    Guards the same division. A supplier concentration of "100%" when the total
    is zero would be a confident statement about a company that has no
    suppliers.
    """
    if total == 0:
        return Absent.NO_BASELINE
    return (amount / total) * 100.0


def composite(scores: dict[str, float], weights: dict[str, float]) -> float | Absent:
    """A single score from several, clamped to 0–100.

    Clamped because a composite that reads 104 tells a founder the number is
    made up, and they would be right. The clamp is a symptom check: if inputs
    routinely exceed the range, the weights are wrong and the clamp is hiding it
    — which is why the boundary has its own test rather than being assumed.
    """
    result = weighted(scores, weights)
    if isinstance(result, Absent):
        return result
    return max(0.0, min(100.0, result))
