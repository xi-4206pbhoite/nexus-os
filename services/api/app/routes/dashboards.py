"""The seven director pages, and where a person lands.

Placeholders in the honest sense: the shell, the offering list and every
capability-to-source mapping are real and come from doc 05, and **no tile
carries a value**, because none has been computed yet. M8 and M9 fill them in
through `calculators/`, which is pure.

Two boundaries are enforced here rather than in the UI, and both are doc 06:

- **§2.3** — a caller reaching a department they do not hold gets a 404, via
  `enforce_department`. Not 403: *"this exists and you may not have it"* is an
  existence disclosure about how the company is organised.
- **§2.4** — the Chief of Staff page is Owner and Executive only, so a
  Department Manager's portal is six directors rather than seven. That cost is
  acknowledged in the document and is not softened here.

The list endpoint returns only the directors the caller may open. It does not
return the others marked "locked", and it carries no count of what was removed —
doc 06 §4.5, the same rule `filter_records` follows.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.db import _unscoped_session
from app.deps import CurrentScope
from app.deps_scope import enforce_department
from app.domain.dashboards import (
    BY_DEPARTMENT,
    DELIVERED,
    DIRECTORS,
    Director,
    Offering,
    Source,
    landing_department,
    state_for,
    unlock_sentence,
)
from app.domain.department_answers import BINDING_ONLY_SQL
from app.domain.departments import selected_departments

# Aliased: `BY_DEPARTMENT` already means the dashboard *offerings* here, and two
# dictionaries with one name is how the wrong one gets read.
from app.domain.question_bank import BY_DEPARTMENT as QUESTIONS_BY_DEPARTMENT
from app.domain.scopes import Department

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def connected_sources() -> frozenset[Source]:
    """What this workspace actually has wired up.

    Empty, and honestly so. Document upload exists (M5) but nothing yet reads an
    indexed document into a dashboard, and no integration exists at all before
    M10. Returning `{DOCUMENTS}` here because the upload route exists would make
    every tile that needs documents claim to be one step from working.

    This is the single place that changes as connectors land, and it takes no
    arguments today for the same reason: a per-workspace answer needs the
    integration registry that M10 introduces, and inventing a shape for it now
    would be guessing at the wrong problem.
    """
    return frozenset()


class OfferingOut(BaseModel):
    id: str
    name: str
    shows: str
    state: str
    unlock: str
    """What this needs, in words. Empty only when nothing is missing."""
    needs: list[str]
    phase: int
    note: str


class DirectorOut(BaseModel):
    department: str
    title: str
    remit: str
    scoreable: bool
    path: str
    offerings: list[OfferingOut]


class DirectorSummary(BaseModel):
    department: str
    title: str
    remit: str
    scoreable: bool
    path: str
    offering_count: int
    unanswered_questions: int = 0
    """Q27. How many of this department's questions are still unanswered.

    The founder answers their own department during onboarding and defers the
    rest, so most directors start here with a number. It belongs on the director
    because that is where the deferral becomes concrete: a dashboard that cannot
    yet compute anything should say **what would turn it on**, not sit empty.

    Zero means the block is complete. A director with no block — the Chief of
    Staff — is always zero, because it consumes the other directors rather than
    asking anything of its own.
    """


class DashboardsOut(BaseModel):
    directors: list[DirectorSummary]
    landing: str | None
    """Where to send this caller. `None` when they hold no department — which
    happens to a Viewer, and is a state to render rather than a redirect."""

    delivered_count: int
    """How many offerings across the whole product have an implementation. Zero
    today. Shown so the page cannot imply more than exists."""


def _path(department: Department) -> str:
    return f"/dashboard/{department.value}"


def _offering_out(offering: Offering, connected: frozenset[Source]) -> OfferingOut:
    return OfferingOut(
        id=offering.id,
        name=offering.name,
        shows=offering.shows,
        state=state_for(offering, connected=connected).value,
        unlock=unlock_sentence(offering, connected=connected),
        needs=[source.value for source in offering.needs],
        phase=offering.phase,
        note=offering.note,
    )


# Built once, so the `S608` justification sits in one place. `BINDING_ONLY_SQL`
# is a module constant and never input; it is interpolated because every reader
# of department facts must use the *same* predicate, and a copy per query is how
# one ends up missing it.
_ANSWERED_SQL = (
    "SELECT department, question_key FROM onboarding_answer"  # noqa: S608
    f" WHERE department IS NOT NULL AND {BINDING_ONLY_SQL}"
)


async def running_departments(scope: CurrentScope) -> frozenset[Department]:
    """Which departments this company runs (Q22/Q63).

    A dependency rather than a call inside the handler, so the route stays a
    pure function of its inputs and `tests/test_dashboard_scope.py` can keep
    asserting the *permission* lattice without standing up a database. Reading
    it inline turned four unit tests into integration tests, which is a real
    cost and not one this filter is worth.
    """
    async with _unscoped_session() as db:
        return await selected_departments(db, workspace_id=scope.workspace_id)


RunningDepartments = Annotated[frozenset[Department], Depends(running_departments)]


async def answered_questions(scope: CurrentScope) -> frozenset[tuple[str, str]]:
    """Which department questions already have a **binding** answer (Q27).

    A dependency for the same reason `running_departments` is one, and this is
    the second time that lesson has been learned in this file: reading it inline
    turns four permission unit tests into integration tests, because they assert
    the lattice and have no database.

    One query for the whole dashboard list rather than one per director — six
    round trips to render a screen is how it becomes slow before it holds any
    data.
    """
    async with _unscoped_session() as db:
        await db.execute(
            text("SELECT set_config('nexus.workspace_id', :w, true)"),
            {"w": str(scope.workspace_id)},
        )
        rows = (await db.execute(text(_ANSWERED_SQL))).all()
    return frozenset((r.department, r.question_key) for r in rows)


AnsweredQuestions = Annotated[frozenset[tuple[str, str]], Depends(answered_questions)]


def _reachable(scope: CurrentScope, director: Director) -> bool:
    if director.executive_only:
        return scope.can_see_executive_surface
    return scope.may_reach_department(director.department)


@router.get("", response_model=DashboardsOut)
async def list_dashboards(
    scope: CurrentScope, chosen: RunningDepartments, answered: AnsweredQuestions
) -> DashboardsOut:
    """The directors this caller may open, and where to land them.

    **Two filters, and they answer different questions.** Which departments the
    *company runs* (Q22/Q63, chosen during onboarding) decides which directors
    exist at all; which the *caller may reach* decides who sees them. A company
    that does not run a sales function should show no Sales Director to anybody,
    including its Owner — an empty dashboard reads as broken data rather than as
    an absent department, which is the whole reason selection exists.

    A workspace that has not chosen yet gets all seven. That is the honest
    default: nothing has been said about this company, so nothing has been ruled
    out, and hiding directors from someone who never made a choice would be the
    product deciding on their behalf.
    """
    # `selected_departments` always includes the Chief of Staff, so a workspace
    # with exactly one entry has chosen nothing.
    has_chosen = len(chosen) > 1

    visible = [
        d for d in DIRECTORS if _reachable(scope, d) and (not has_chosen or d.department in chosen)
    ]

    landing = landing_department(
        executive_surface=scope.can_see_executive_surface,
        departments=scope.departments,
    )

    def outstanding(department: Department) -> int:
        # A proposed answer does not count as answered. A block that looked
        # complete because a Contributor filled it in would hide the very thing
        # the review gate exists to surface.
        return sum(
            1
            for q in QUESTIONS_BY_DEPARTMENT.get(department, ())
            if (department.value, q.key) not in answered
        )

    return DashboardsOut(
        directors=[
            DirectorSummary(
                department=d.department.value,
                title=d.title,
                remit=d.remit,
                scoreable=d.scoreable,
                path=_path(d.department),
                unanswered_questions=outstanding(d.department),
                offering_count=len(d.offerings),
            )
            for d in visible
        ],
        landing=_path(landing) if landing else None,
        delivered_count=len(DELIVERED),
    )


@router.get("/{department}", response_model=DirectorOut)
async def director_dashboard(department: Department, scope: CurrentScope) -> DirectorOut:
    """One director's page.

    `enforce_department` is what refuses a department the caller does not hold,
    and it 404s. The executive check is separate because it is a different rule
    with a different answer: the Chief of Staff page is not a department someone
    might be added to, so naming the requirement is safe and useful.
    """
    director = BY_DEPARTMENT.get(department)
    if director is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    if director.executive_only and not scope.can_see_executive_surface:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The Chief of Staff view requires an Owner or Executive role.",
        )

    enforce_department(scope, director.department)

    connected = connected_sources()
    return DirectorOut(
        department=director.department.value,
        title=director.title,
        remit=director.remit,
        scoreable=director.scoreable,
        path=_path(director.department),
        offerings=[_offering_out(offering, connected) for offering in director.offerings],
    )
