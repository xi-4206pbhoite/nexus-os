"""The department block: who is asked, and how the answers are classified.

Doc 08 §2-§7 gives each department five questions only that department can answer.
Two rules decide whether one appears, and they are independent:

1. **The company runs that department** (doc 08 §1.6, a multi-select).
2. **The caller can reach it** (doc 08 §0 — *"a Sales Executive is never asked when
   the financial year ends"*).

The subtle part, and what D15 warned about, is that **`asked_of` and `department`
are different fields**. `asked_of` routes; `department` classifies at L3. Doc 08
§3.1's pipeline stages are asked of Sales and classified L2, because they are
structural rather than sensitive — collapsing the two fields would have hidden them
from a Viewer for no reason. Doc 08 §4.3's spend threshold is asked of Finance *and*
classified L3 Finance, so there the two agree.

Where doc 08 and doc 06 disagree, doc 06 wins and these tests pin the result. Doc 08
§0 says every answer is L1 or L2; doc 06 §2.5 says a money threshold arriving through
a form is not a company fact. Five questions are therefore L3, and
`test_the_sensitive_department_answers_are_not_company_wide` is what stops someone
"simplifying" them back to L2.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.onboarding import (
    BY_KEY,
    DEPARTMENT_QUESTIONS,
    SCOREABLE_DEPARTMENTS,
    Pass,
    questions_for,
    questions_for_departments,
    scope_for_answer,
)
from app.domain.scopes import Department, Role, Scope
from app.domain.session import ScopedSession
from app.routes.setup import _selection_after, departments_selected, may_be_asked

ALL_SIX = frozenset(
    {
        Department.MARKETING,
        Department.SALES,
        Department.FINANCE,
        Department.OPERATIONS,
        Department.HR,
        Department.STRATEGY,
    }
)


def scope_for(role: Role, departments: frozenset[Department]) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        workspace_id=uuid4(),
        tenant_id=uuid4(),
        role=role,
        departments=departments,
    )


OWNER = scope_for(Role.OWNER, frozenset({Department.EXECUTIVE}))
SALES_MANAGER = scope_for(Role.DEPARTMENT_MANAGER, frozenset({Department.SALES}))


# ── The catalogue's shape ──────────────────────────────────────


def test_every_department_question_names_the_block_it_belongs_to() -> None:
    """Without `asked_of` a question cannot be routed, and would be asked of everyone."""
    assert all(q.asked_of is not None for q in DEPARTMENT_QUESTIONS)
    assert all(q.stage is Pass.DEPARTMENT for q in DEPARTMENT_QUESTIONS)


def test_the_executive_department_is_never_asked_anything() -> None:
    """It consumes the others and produces no data of its own (doc 05 §10).

    This is also why the composite score is out of six, and why doc 08 §1.6's
    arithmetic of "seven blocks, 39 fields" cannot be right — see ADR 0015.
    """
    assert Department.EXECUTIVE not in {q.asked_of for q in DEPARTMENT_QUESTIONS}
    assert Department.EXECUTIVE.value not in {c.value for c in SCOREABLE_DEPARTMENTS}
    assert len(SCOREABLE_DEPARTMENTS) == 6


def test_each_department_is_asked_between_four_and_five_questions() -> None:
    """Doc 08 lists five each. Two departments have four here, and deliberately:
    §2.3 and §4.1 already exist company-wide as `monthly_marketing_budget` and
    `fiscal_year_start`, so asking them again would put one fact in two rows."""
    counts = {
        department: len([q for q in DEPARTMENT_QUESTIONS if q.asked_of is department])
        for department in ALL_SIX
    }
    assert all(4 <= n <= 5 for n in counts.values()), counts
    assert counts[Department.MARKETING] == 4, "§2.3 is monthly_marketing_budget"
    assert counts[Department.FINANCE] == 4, "§4.1 is fiscal_year_start"


def test_the_reused_questions_still_exist_company_wide() -> None:
    """If either were ever deleted, a department would silently lose a question."""
    for key in ("monthly_marketing_budget", "fiscal_year_start"):
        assert BY_KEY[key].asked_of is None


# ── Classification: doc 06 §2.5 outranks doc 08 §0 ────────────


SENSITIVE = {
    "spend_approval_threshold": Department.FINANCE,
    "runway_alert_months": Department.FINANCE,
    "supplier_concentration": Department.OPERATIONS,
    "people_risk": Department.HR,
    "target_market": Department.STRATEGY,
}


@pytest.mark.parametrize(("key", "department"), sorted(SENSITIVE.items()))
def test_the_sensitive_department_answers_are_not_company_wide(
    key: str, department: Department
) -> None:
    """Doc 08 §0 says the whole set is L1 or L2. For these five it is wrong.

    Doc 06 §2.5: *"They are not 'company facts' visible to everyone merely because
    they arrived through a form."* A runway threshold discloses how close to the edge
    the company is; a people risk names an individual. A Viewer reaches L2 and must
    not reach either.
    """
    scope, owning_department = scope_for_answer(key)

    assert scope is Scope.L3_DEPARTMENT
    assert owning_department is department


def test_no_department_answer_is_company_public() -> None:
    """L1 means it leaves the building. None of these do."""
    l1 = [q.key for q in DEPARTMENT_QUESTIONS if q.scope is Scope.L1_COMPANY_PUBLIC]
    assert l1 == []


def test_an_l3_department_answer_always_names_its_department() -> None:
    """A CHECK constraint forbids storing L3 with no department, and an L3 row with
    no department is reachable by anyone holding any L3 access."""
    for question in DEPARTMENT_QUESTIONS:
        if question.scope is Scope.L3_DEPARTMENT:
            assert question.department is not None, question.key


def test_asked_of_and_department_are_not_the_same_field() -> None:
    """D15's warning, asserted. If they had been collapsed, every Sales question
    would be an L3 Sales fact and the pipeline stages would be hidden from a Viewer.

    So there must exist a question routed to a department and classified below L3.
    """
    structural = [
        q for q in DEPARTMENT_QUESTIONS if q.asked_of is not None and q.department is None
    ]
    assert structural, "collapsing the two fields would make this list empty"
    assert BY_KEY["pipeline_stages"].asked_of is Department.SALES
    assert BY_KEY["pipeline_stages"].department is None


# ── Narrowing 1: the company runs it ──────────────────────────


def test_no_department_questions_before_anything_is_selected() -> None:
    """The stage is empty rather than showing all 28 to a company that runs two."""
    assert questions_for_departments(frozenset()) == ()


def test_selecting_one_department_serves_only_its_block() -> None:
    served = questions_for_departments(frozenset({Department.SALES}))

    assert served
    assert {q.asked_of for q in served} == {Department.SALES}


def test_selecting_all_six_serves_every_question() -> None:
    assert len(questions_for_departments(ALL_SIX)) == len(DEPARTMENT_QUESTIONS)


def test_an_unselected_department_is_absent_not_disabled() -> None:
    """Doc 08 §2.2's principle applied to the form.

    A channel that is not run is reported as *not run*, never as zero. A department
    the company does not have should not be a row of greyed-out inputs implying they
    forgot to fill something in.
    """
    served = questions_for_departments(frozenset({Department.MARKETING}))
    keys = {q.key for q in served}

    assert "pipeline_stages" not in keys
    assert "runway_alert_months" not in keys


# ── Narrowing 2: the caller reaches it ────────────────────────


def test_an_owner_is_asked_every_selected_department() -> None:
    """Owner holds all departments, so selection is the only narrowing."""
    for question in questions_for_departments(ALL_SIX):
        assert may_be_asked(OWNER, question, ALL_SIX)


def test_a_sales_manager_is_never_asked_about_finance() -> None:
    """Doc 08 §0, verbatim: a Sales Executive is never asked when the financial year
    ends. The check is `may_reach_department`, the same call the dashboards make."""
    finance = BY_KEY["spend_approval_threshold"]
    sales = BY_KEY["pipeline_stages"]

    assert may_be_asked(SALES_MANAGER, sales, ALL_SIX) is True
    assert may_be_asked(SALES_MANAGER, finance, ALL_SIX) is False


def test_company_wide_questions_are_unaffected_by_either_narrowing() -> None:
    """They have no `asked_of`, so a company running nothing still gets asked them."""
    for question in questions_for(Pass.ONE):
        assert may_be_asked(SALES_MANAGER, question, frozenset())


# ── Reading the selection back ────────────────────────────────


def test_the_selection_is_read_from_the_companys_own_answer() -> None:
    selected = departments_selected({"departments_run": ["sales", "finance"]})
    assert selected == {Department.SALES, Department.FINANCE}


def test_an_absent_selection_is_empty_rather_than_everything() -> None:
    """Defaulting to all six would ask a two-person company 28 questions it never
    agreed to, which is the opposite of doc 08's "only ask what only they know"."""
    assert departments_selected({}) == frozenset()


@pytest.mark.parametrize("stored", [["not_a_department"], "sales", None, 7])
def test_an_unreadable_selection_offers_no_block(stored: object) -> None:
    """A value the enum no longer knows means the enum changed under an existing
    row. Stop offering the block rather than failing the whole wizard — the user can
    still reach every company-wide question and re-select."""
    assert departments_selected({"departments_run": stored}) == frozenset()


# ── The write path narrows too ────────────────────────────────


def test_the_batch_decides_the_selection_when_it_sets_one() -> None:
    """A client may select a department and answer its questions in one request.

    Judging that batch against the *previous* selection would refuse the second half
    of a coherent submission — an ordering trap rather than a rule. Verified live:
    selecting Finance and answering `runway_alert_months` together returns 200.
    """
    batch = {BY_KEY["departments_run"]: ["sales", "finance"]}

    assert _selection_after(batch, frozenset({Department.MARKETING})) == {
        Department.SALES,
        Department.FINANCE,
    }


def test_the_stored_selection_stands_when_the_batch_does_not_set_one() -> None:
    batch = {BY_KEY["pipeline_stages"]: "Enquiry, Won"}
    stored = frozenset({Department.SALES})

    assert _selection_after(batch, stored) == stored


def test_deselecting_everything_in_a_batch_leaves_nothing_selected() -> None:
    """`departments_run` is required, so an empty list is refused by validation before
    reaching here. This asserts the resolver does not silently fall back to the old
    selection if that ever changes."""
    batch = {BY_KEY["departments_run"]: []}

    assert _selection_after(batch, frozenset({Department.SALES})) == frozenset()
