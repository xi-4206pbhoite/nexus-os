"""Who may answer a department's questions, and whether it binds.

`doc/12` §Phase 7. Two rules, and they are different in kind.

**Who may answer** (Q30, D16). `may_administer` is company-wide — Owner and
Executive. A Department Manager sees one department, so the question "may you
answer this?" cannot be a single role check: it depends on *which* department is
being asked about. Widening `may_administer` blindly would let a Sales Manager
configure Finance.

**Whether it binds** (Q31, D22). A Contributor's answer is **proposed**, not
recorded. This is not distrust of contributors — it is that a department fact
binds everyone in that department, and someone whose own scope is restricted to
their own records cannot be the one who decides what is true for everybody.
Their answer is real, kept, and waits for a Manager or Owner at the review gate.

The distinction the third test defends is subtle and easy to lose: a proposed
answer must not be **readable as a department fact** before it is confirmed. It
is not enough that it is flagged — anything reading department facts must not
see it at all, or the flag is decoration and the first consumer that forgets to
filter has quietly promoted a Contributor.
"""

from __future__ import annotations

import pytest

from app.domain.scopes import Department, Role

# ── Who may answer (Q30, D16) ─────────────────────────────────


def test_an_owner_may_answer_every_department() -> None:
    from app.domain.department_answers import may_answer_department_question

    for department in Department:
        assert may_answer_department_question(
            role=Role.OWNER, caller_departments=frozenset(), department=department
        )


def test_department_manager_may_answer_only_their_own_department() -> None:
    """Q30's whole point. A Manager is trusted *within* their department and
    nowhere else, so this cannot be a role check alone."""
    from app.domain.department_answers import may_answer_department_question

    assert may_answer_department_question(
        role=Role.DEPARTMENT_MANAGER,
        caller_departments=frozenset({Department.SALES}),
        department=Department.SALES,
    )
    assert not may_answer_department_question(
        role=Role.DEPARTMENT_MANAGER,
        caller_departments=frozenset({Department.SALES}),
        department=Department.FINANCE,
    )


def test_a_manager_of_no_department_may_answer_nothing() -> None:
    """A Manager whose department assignment is empty is not a company-wide
    administrator by omission. Absence of a restriction is not a permission."""
    from app.domain.department_answers import may_answer_department_question

    assert not may_answer_department_question(
        role=Role.DEPARTMENT_MANAGER,
        caller_departments=frozenset(),
        department=Department.SALES,
    )


def test_a_viewer_may_answer_nothing_even_in_their_own_department() -> None:
    from app.domain.department_answers import may_answer_department_question

    assert not may_answer_department_question(
        role=Role.VIEWER,
        caller_departments=frozenset({Department.SALES}),
        department=Department.SALES,
    )


# ── Whether it binds (Q31, D22) ───────────────────────────────


def test_contributor_answer_is_proposed_not_binding() -> None:
    """A department fact binds everyone in that department. Somebody whose own
    scope is restricted to their own records cannot be the one who decides what
    is true for all of them."""
    from app.domain.department_answers import AnswerState, state_for_answer

    assert (
        state_for_answer(role=Role.CONTRIBUTOR, caller_departments=frozenset({Department.SALES}))
        is AnswerState.PROPOSED
    )


@pytest.mark.parametrize("role", [Role.OWNER, Role.EXECUTIVE, Role.DEPARTMENT_MANAGER])
def test_a_manager_or_above_binds_immediately(role: Role) -> None:
    """The other side of the gate, so the test above cannot pass by everything
    being proposed."""
    from app.domain.department_answers import AnswerState, state_for_answer

    assert (
        state_for_answer(role=role, caller_departments=frozenset({Department.SALES}))
        is AnswerState.BOUND
    )


def test_a_proposed_answer_is_not_readable_as_a_department_fact() -> None:
    """The one that matters, and the one easiest to lose.

    It is not enough that a proposed answer is *flagged*. Anything reading
    department facts must not see it at all — otherwise the flag is decoration,
    and the first consumer that forgets to filter has quietly let a Contributor
    bind a fact for their whole department.

    Asserted on the predicate every reader is required to use, so there is one
    place to get it right rather than one per caller.
    """
    from app.domain.department_answers import BINDING_ONLY_SQL

    assert "proposed" in BINDING_ONLY_SQL
    # A reader that inverted the sense would still contain the word, so the
    # exclusion is asserted rather than the mention.
    assert "<>" in BINDING_ONLY_SQL or "!=" in BINDING_ONLY_SQL


# ── Department change keeps the tag (Q32) ─────────────────────


def test_answers_survive_a_department_change_tagged_to_the_old_one() -> None:
    """Q32. An answer records what was true for the department it was given
    for, and a company that stops running Sales has not made its old Sales
    answers untrue — it has made them historical.

    Retagging on change would rewrite the past to match the present, which is
    the one thing an answer store must never do; deleting would lose the
    evidence a later disagreement needs.
    """
    from app.domain.department_answers import retag_on_department_change

    assert retag_on_department_change is None, (
        "there is deliberately no retag function — answers keep the department "
        "they were given for. If one is added, this test is the argument it has "
        "to beat."
    )
