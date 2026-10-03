"""Every question in the bank earns its place.

`doc/12` §Phase 7, Q33. The rule is one sentence — *cut any question no
capability consumes* — and it needs a test because the pressure runs the other
way. Nobody ever proposes thirty-nine questions; they propose one, and it would
be useful to know, and it is only one more screen.

An earlier draft of `doc/08` carried thirty-nine. This bank carries
**twenty-nine**, and the arithmetic is in `test_the_bank_is_five_per_department`
so a drift shows up as a number rather than as a feeling.
"""

from __future__ import annotations

import pytest

from app.domain.question_bank import BANK, BY_DEPARTMENT
from app.domain.scopes import Department, Scope


def test_every_question_is_consumed_by_a_declared_capability() -> None:
    """The guard the phase exists to install.

    A question with no consumer is a form field: it costs a founder the same
    attention as a real question and changes nothing they will ever see.
    """
    orphans = [q.key for q in BANK if not q.consumed_by.strip()]
    assert orphans == [], (
        f"{orphans} declare no capability that reads them. Name the capability, "
        "or cut the question — those are the only two options Q33 allows."
    )


def test_capability_names_are_namespaced() -> None:
    """`marketing.growth_planner`, not `growth_planner`.

    Two departments will eventually both have a "forecast", and a bare name
    makes the collision invisible — the second one to be added silently reads
    as the first.
    """
    unqualified = [q.key for q in BANK if "." not in q.consumed_by]
    assert unqualified == [], f"{unqualified} name a capability with no namespace"


def test_the_bank_is_five_per_department_minus_the_recorded_cut() -> None:
    """Twenty-nine, not thirty, and not thirty-nine.

    `doc/08` asks five per department across six departments. Finance is four:
    its "when does your financial year end?" is cut, because P6's company stage
    already asks when it *starts* and the same fact asked from both ends is two
    rows that can disagree. ADR 0020 records it.
    """
    counts = {d.value: len(qs) for d, qs in BY_DEPARTMENT.items()}
    assert counts == {
        "marketing": 5,
        "sales": 5,
        "finance": 4,
        "operations": 5,
        "hr": 5,
        "strategy": 5,
    }, counts
    assert len(BANK) == 29


def test_no_question_duplicates_the_company_stage() -> None:
    """The cut above is a rule, not a one-off.

    A department question that re-asks something the company stage already
    covers produces two rows for one fact, and nothing decides which wins when
    they disagree.
    """
    from app.domain.onboarding import COMPANY_QUESTIONS

    company = {q.key for q in COMPANY_QUESTIONS}
    clashes = sorted({q.key for q in BANK} & company)
    assert clashes == [], f"{clashes} are asked twice — once company-wide, once by department"


def test_keys_are_unique_across_the_bank() -> None:
    """A duplicate key does not raise; the later definition silently wins. That
    already happened once in P6, which is why it is asserted here too."""
    keys = [q.key for q in BANK]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert duplicates == [], duplicates


@pytest.mark.parametrize("department", list(BY_DEPARTMENT))
def test_each_question_is_owned_by_the_department_that_asks_it(
    department: Department,
) -> None:
    """Doc 06 §2.5 — tagged at capture. A question filed under the wrong
    department would store its answer where that department's manager cannot
    reach it, and the failure would look like missing data."""
    for question in BY_DEPARTMENT[department]:
        assert question.department is department, (
            f"{question.key} is asked by {department.value} and owned by {question.department}"
        )


def test_department_answers_bind_at_l3_unless_argued_otherwise() -> None:
    """A department fact is L3 by default.

    One question is deliberately higher — whether to track visa and document
    expiry, which decides if the product holds immigration documents at all.
    That is a decision about people rather than about a department, so it sits
    at L4 with the reason at its definition. The test names it so a second
    exception has to be argued rather than added.
    """
    exceptions = {q.key: q.scope for q in BANK if q.scope is not Scope.L3_DEPARTMENT}
    assert exceptions == {"track_document_expiry": Scope.L4_RESTRICTED}, exceptions
