"""The capability registry, and the two numbers derived from it.

`doc/12` P15 (D8, Q64). The rule that shapes the whole module: **no literal 6,
no literal 21 or 24, anywhere.**

A denominator written as a number is a claim nobody re-checks. "Scored out of
six departments" was true when somebody counted, and stays on the screen after a
seventh becomes scoreable or a company selects four. Deriving it means the
screen cannot disagree with the product — and a founder who counts the tiles and
gets a different answer has found a reason to distrust every other number we
show them.

**`delivered` is a property of the entry, not a hand-maintained set.**
`DELIVERED: frozenset[str] = frozenset()` was the old mechanism: honest, and a
second place to remember. A capability is delivered when it has an
implementation, so the registry says so and nothing else needs updating.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.domain.dashboards import DIRECTORS, Source
from app.domain.scopes import Department


@dataclass(frozen=True, slots=True)
class Capability:
    """What one capability needs and whether it counts toward a score."""

    id: str
    department: Department
    name: str
    required_sources: tuple[Source, ...]
    consumes_facts: tuple[str, ...]
    """Fact keys this capability reads. Its length feeds the review gate's
    impact ranking — a fact is important because things depend on it."""

    scoreable: bool
    delivered: bool = False
    """Whether an implementation exists. Zero today, and the honesty of every
    "planned" label rests on this staying accurate."""


def _from_directors() -> tuple[Capability, ...]:
    """Built from `DIRECTORS` so the registry cannot drift from the offerings.

    Two hand-maintained lists of the same thing is the failure this module
    exists to prevent — deriving one from the other means adding an offering
    updates the registry, the denominator and the completeness meter at once.
    """
    return tuple(
        Capability(
            id=offering.id,
            department=director.department,
            name=offering.name,
            required_sources=offering.needs,
            consumes_facts=(),
            scoreable=director.scoreable,
        )
        for director in DIRECTORS
        for offering in director.offerings
    )


REGISTRY: Final[tuple[Capability, ...]] = _from_directors()


# A department may be structurally scoreable and still have nothing to score
# with. `doc/05` §3.1: **Marketing is not scoreable without GA4**, and the brand
# and SEO audit scores must not be merged into a Marketing score to manufacture
# one — they measure the website, not the marketing.
#
# Declared as data so the exception is visible next to the rule rather than
# buried in a branch. An empty tuple means "nothing required beyond the
# department existing", which is the common case.
REQUIRED_FOR_SCORING: Final[dict[Department, tuple[Source, ...]]] = {
    Department.MARKETING: (Source.GA4,),
}


class ScoreableUnit(StrEnum):
    """What the composite score is out of. **Not the same set as `Department`.**

    ADR 0010: *"Customers is scoreable but lives inside the Sales director
    rather than having a page."* That sentence is the whole reason this type
    exists separately.

    Customers is deliberately **not** a `Department`. A department is something
    a person belongs to: it appears in onboarding selection, it goes on a
    membership, and it scopes L3 rows through RLS. Customers is none of those —
    nobody is "in Customers", and adding it to that enum would make it
    selectable, assignable and permission-bearing to fix a counting problem.

    So: six units, five of which happen to be departments with pages, and one
    which is scored inside Sales. Finding #27, resolved this way rather than by
    widening `Department` — the blast radius of that enum is ten modules and
    every RLS policy that reads a department array.
    """

    MARKETING = "marketing"
    SALES = "sales"
    FINANCE = "finance"
    OPERATIONS = "operations"
    HR = "hr"

    CUSTOMERS = "customers"
    """Retention, satisfaction, concentration. Scored, and shown on the Sales
    director's page because that is where the people who act on it already are."""


# Which department has to be running for a unit to be scored. Customers is the
# only entry that differs from its own name, and it is why this is a mapping
# rather than an identity function.
UNIT_REQUIRES_DEPARTMENT: Final[dict[ScoreableUnit, Department]] = {
    ScoreableUnit.MARKETING: Department.MARKETING,
    ScoreableUnit.SALES: Department.SALES,
    ScoreableUnit.FINANCE: Department.FINANCE,
    ScoreableUnit.OPERATIONS: Department.OPERATIONS,
    ScoreableUnit.HR: Department.HR,
    ScoreableUnit.CUSTOMERS: Department.SALES,
}


def scoreable_units(
    selected: frozenset[Department], *, connected: frozenset[Source] | None = None
) -> frozenset[ScoreableUnit]:
    """The units this company is scored out of.

    A company running Sales is scored on **Sales and Customers** — two units,
    one department. That is ADR 0010's arrangement made real, and it is why the
    denominator was never going to equal the number of director pages.

    Marketing still needs GA4 (`REQUIRED_FOR_SCORING`), and the connector rule
    is applied per **unit** against the department it depends on.
    """
    return frozenset(
        unit
        for unit, department in UNIT_REQUIRES_DEPARTMENT.items()
        if department in selected
        and (
            connected is None
            or all(source in connected for source in REQUIRED_FOR_SCORING.get(department, ()))
        )
    )


def scoreable_departments(
    selected: frozenset[Department], *, connected: frozenset[Source] | None = None
) -> frozenset[Department]:
    """The departments with a director page that count toward the composite.

    Both filters matter. A department the company does not run cannot be scored
    — judging them on a function they told us they do not have is worse than
    showing no score. And Chief of Staff and Strategy are never scored: they are
    synthesis layers reading the others, so including them counts the same work
    twice.

    **This is not what the score is out of** — `scoreable_units` is. It returns
    the five departments that have a director page and are scored; Customers is
    a sixth *unit* with no page (ADR 0010), which is what finding #27 turned out
    to be. Kept because "which department pages carry a score" is still a real
    question, asked by the shell when it decides where to show one.
    """
    structural = {
        capability.department
        for capability in REGISTRY
        if capability.scoreable and capability.department in selected
    }

    if connected is None:
        # No connector information supplied: report what could be scored, which
        # is what the registry alone can honestly say. Callers that know what is
        # connected pass it and get the narrower, truer answer.
        return frozenset(structural)

    return frozenset(
        department
        for department in structural
        if all(source in connected for source in REQUIRED_FOR_SCORING.get(department, ()))
    )


def score_denominator(
    selected: frozenset[Department], *, connected: frozenset[Source] | None = None
) -> int:
    """The number under the composite score. **Derived, never written down.**

    A company running three departments is scored out of three. Showing them
    "out of six" reports a number that is low for a reason having nothing to do
    with their business.

    Counts only what has a director page — see `scoreable_departments` and
    finding #27 for why that is five and not six, and why the honest thing is to
    show the number the product can actually justify.
    """
    return len(scoreable_units(selected, connected=connected))


def completeness(selected: frozenset[Department]) -> tuple[int, int]:
    """`(delivered, total)` for the capabilities this company can reach.

    Returned as a pair rather than a percentage so the caller can render "0 of
    24" — a percentage hides the denominator, and the denominator is the part
    that makes the claim checkable.
    """
    reachable = [c for c in REGISTRY if c.department in selected]
    return sum(1 for c in reachable if c.delivered), len(reachable)


def capabilities_for(department: Department) -> tuple[Capability, ...]:
    return tuple(c for c in REGISTRY if c.department is department)


def consumers_of(fact_key: str) -> tuple[str, ...]:
    """Which capabilities declare a dependency on a fact.

    This is the review gate's impact score (Q59): a fact matters because things
    depend on it, and that dependency is declared here rather than guessed from
    how often the fact is mentioned.
    """
    return tuple(c.id for c in REGISTRY if fact_key in c.consumes_facts)
