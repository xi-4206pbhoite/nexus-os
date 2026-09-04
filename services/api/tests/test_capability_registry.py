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
    scoreable_units,
)
from app.domain.scopes import Department


def test_the_denominator_follows_the_company_not_a_constant() -> None:
    """The property the whole module exists for."""
    # Three departments, **four** units: Sales brings Customers with it. The
    # denominator counts what is scored, not what was selected, and those stopped
    # being the same number when #27 was resolved.
    three = frozenset({Department.FINANCE, Department.SALES, Department.MARKETING})
    assert score_denominator(three) == 4

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


def test_the_denominator_is_six_because_customers_is_a_unit_without_a_page() -> None:
    """Finding #27, resolved. ADR 0010's six, derived rather than asserted.

    Five departments have a director page and are scored. Customers is the
    sixth: scored, and shown inside the Sales director because that is where
    the people who act on it already are.

    The test that used to live here asserted **five** and said to delete it if
    somebody resolved the discrepancy. This is that deletion, and the assertion
    it leaves behind is the one worth keeping — six, arrived at by counting
    units rather than by writing `6` down.
    """
    assert score_denominator(frozenset(Department)) == 6


def test_a_company_running_sales_is_scored_on_two_units() -> None:
    """One department, two units. That is ADR 0010's arrangement made real, and
    it is why the denominator was never going to equal the number of pages."""
    units = scoreable_units(frozenset({Department.SALES}))
    assert {u.value for u in units} == {"sales", "customers"}


def test_customers_is_not_a_department_anybody_belongs_to() -> None:
    """The reason it is a `ScoreableUnit` and not a `Department`.

    A department is something a person is *in*: it appears in onboarding
    selection, goes on a membership, and scopes L3 rows through RLS. Nobody is
    "in Customers", and adding it to that enum to fix a counting problem would
    have made it selectable, assignable and permission-bearing.
    """
    assert "customers" not in {d.value for d in Department}


def test_a_company_without_sales_is_not_scored_on_customers() -> None:
    """Customers depends on Sales running. Scoring it otherwise would judge a
    company on customer retention it has no function to manage."""
    units = scoreable_units(frozenset({Department.FINANCE}))
    assert {u.value for u in units} == {"finance"}


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


# ── The shell carries its denominator (P15) ───────────────────


def test_the_shell_never_reports_a_score_of_zero() -> None:
    """I10. Nothing is delivered, so nothing is computable — and `0` would be a
    statement about the customer's business rather than about our data.

    This is the failure the whole phase guards against: a dashboard showing
    0/100 to a company that has simply connected nothing looks like a verdict.
    """
    from app.routes.dashboards import ShellOut

    shell = ShellOut(
        score=None, score_denominator=3, capabilities_delivered=0, capabilities_total=24
    )
    assert shell.score is None
    assert shell.score_denominator == 3, "the denominator travels with the score"


def test_the_assistant_panel_is_reserved_rather_than_absent() -> None:
    """Q67. A blank region where a feature is coming reads as a bug; a fake one
    reads as a lie. Reserved, with an honest empty state naming what it will do."""
    from app.routes.dashboards import ShellOut

    assert ShellOut(
        score=None, score_denominator=0, capabilities_delivered=0, capabilities_total=0
    ).assistant_reserved
