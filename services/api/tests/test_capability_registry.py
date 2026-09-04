"""Both numbers are derived. **No literal 6, no literal 21 or 24, anywhere.**

`doc/12` P15. A denominator written as a number is a claim nobody re-checks: it
was true when somebody counted, and it stays on screen after a department is
added or a company selects four. A founder who counts the tiles and gets a
different answer has found a reason to distrust every other number we show.
"""

from __future__ import annotations

from app.domain.registry import (
    REGISTRY,
    capabilities_for,
    completeness,
    consumers_of,
    score_denominator,
    scoreable_departments,
)
from app.domain.scopes import Department


def test_the_denominator_follows_the_company_not_a_constant() -> None:
    """The property the whole module exists for."""
    three = frozenset({Department.FINANCE, Department.SALES, Department.MARKETING})
    assert score_denominator(three) == 3

    one = frozenset({Department.FINANCE})
    assert score_denominator(one) == 1

    assert score_denominator(frozenset()) == 0, (
        "a company that has chosen nothing is scored out of nothing"
    )


def test_synthesis_layers_are_never_scored() -> None:
    """Chief of Staff and Strategy read the other departments. Scoring them
    counts the same work twice."""
    everything = frozenset(Department)
    scoreable = scoreable_departments(everything)

    assert Department.EXECUTIVE not in scoreable
    assert Department.STRATEGY not in scoreable


def test_the_derived_denominator_is_five_and_adr_0010_says_six() -> None:
    """Finding #27, asserted so it cannot be quietly forgotten.

    ADR 0010's sixth scoreable department is **Customers**, which is "scoreable
    but lives inside the Sales director rather than having a page" — so it is
    not a `Department`, has no `DIRECTORS` entry, and nothing derived from
    either can see it.

    This test exists to fail loudly if somebody resolves the discrepancy, which
    is the point: the resolution is a decision for Parul, and until it is made
    the product should show the number it can justify rather than the number a
    document asserts.
    """
    assert score_denominator(frozenset(Department)) == 5, (
        "if this is now 6, finding #27 has been resolved — update it and delete this test"
    )


def test_completeness_returns_a_pair_not_a_percentage() -> None:
    """A percentage hides the denominator, and the denominator is the part that
    makes the claim checkable."""
    delivered, total = completeness(frozenset(Department))
    assert total == len(REGISTRY)
    assert delivered == 0, "nothing is implemented yet, and the meter must say so"


def test_completeness_counts_only_what_the_company_can_reach() -> None:
    """A company running Finance alone should not be told it has completed 0 of
    67 — most of those belong to departments it does not have."""
    _, all_departments = completeness(frozenset(Department))
    _, finance_only = completeness(frozenset({Department.FINANCE}))

    assert finance_only < all_departments
    assert finance_only == len(capabilities_for(Department.FINANCE))


def test_the_registry_is_derived_from_the_offerings() -> None:
    """Two hand-maintained lists of the same thing is the failure this module
    prevents. Adding an offering must update the registry, the denominator and
    the completeness meter at once."""
    from app.domain.dashboards import DIRECTORS

    assert len(REGISTRY) == sum(len(d.offerings) for d in DIRECTORS)


def test_nothing_is_delivered_yet_and_the_registry_says_so() -> None:
    """`DELIVERED: frozenset[str] = frozenset()` was the old mechanism —
    honest, and a second place to remember. The honesty of every "planned" label
    now rests on this flag staying accurate."""
    assert not any(c.delivered for c in REGISTRY)


def test_impact_is_a_declared_dependency_not_a_guess() -> None:
    """Q59's input. A fact matters because things depend on it, and the
    dependency is declared rather than inferred from how often it is mentioned."""
    assert consumers_of("a_fact_nothing_uses") == ()
