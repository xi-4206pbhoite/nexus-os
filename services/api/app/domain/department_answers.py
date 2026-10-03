"""Who may answer a department's questions, and whether the answer binds.

`doc/12` §Phase 7. Two rules, and they are different in kind — which is why
they are two functions rather than one permission check.

**Who may answer** (Q30, D16). `may_administer` is a company-wide question:
Owner and Executive see everything, so they may configure everything. A
Department Manager sees one department, so "may you answer this?" cannot be a
role check alone — it depends on *which* department is being asked about.
Widening `may_administer` to include Managers, without that qualifier, would let
a Sales Manager configure Finance.

**Whether it binds** (Q31, D22). A Contributor's answer is **proposed**, never
recorded as fact. Not distrust: a department fact binds everyone in that
department, and somebody whose own scope is restricted to their own records
cannot be the one who decides what is true for all of them. Their answer is
real, is kept, and waits for a Manager or Owner at the review gate (P13).

**Answers keep the department they were given for** (Q32). There is deliberately
no retag function — see the note at the bottom of this module.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from app.domain.scopes import Department, Role, grant_for


class AnswerState(StrEnum):
    """Whether an answer is a department fact yet.

    Two values, not three. A rejected proposal is deleted with its reason
    recorded in the audit trail rather than kept as a state here — a `rejected`
    row would sit in the answer store for ever being filtered out of every
    query, and the first query that forgot would surface it.
    """

    BOUND = "bound"
    PROPOSED = "proposed"


def may_answer_department_question(
    *, role: Role, caller_departments: frozenset[Department], department: Department
) -> bool:
    """Whether this caller may answer questions for `department` at all.

    Company-wide administrators may answer for any department: that is what
    `all_departments` means, and it is the same property `may_administer` tests.

    A Department Manager may answer for the departments they are assigned to and
    no others. Assignment is the qualifier `may_administer` has no room for, and
    the reason this is a separate function rather than a widened one.

    **A Manager with no assignment may answer nothing.** Absence of a
    restriction is not a permission, and an empty set is the shape a
    half-configured membership takes — it must fail closed.

    Everyone else, including a Contributor in their own department, may not.
    Answering is not the same act as *proposing*: `state_for_answer` decides
    that, and a Contributor reaching this function at all would mean the route
    had already decided they may write.
    """
    grant = grant_for(role)

    if grant.all_departments and grant.executive_surface:
        return True

    if role is Role.DEPARTMENT_MANAGER:
        return department in caller_departments

    return False


def state_for_answer(*, role: Role, caller_departments: frozenset[Department]) -> AnswerState:
    """Whether this caller's answer binds, or waits to be confirmed.

    `caller_departments` is unused today and is in the signature deliberately.
    Q31 is about *authority*, not about which department the answer is for — but
    every caller already has this to hand, and a later rule that does depend on
    it (a Manager proposing outside their own department, say) should not have
    to change every call site to get it.
    """
    del caller_departments  # see the docstring

    grant = grant_for(role)

    # Restricted to their own records, so not the person who decides what is
    # true for a whole department. This is the property rather than the role
    # name, so a role added later with the same restriction inherits it.
    if grant.contributor_restricted:
        return AnswerState.PROPOSED

    return AnswerState.BOUND


# Every read of department facts must carry this. Kept as one constant rather
# than repeated in each query, because a proposed answer that is merely
# *flagged* is not protected: the flag only works if nothing reading facts can
# see it, and one caller forgetting the filter would silently let a Contributor
# bind a fact for their whole department.
BINDING_ONLY_SQL: Final[str] = "answer_state <> 'proposed'"


# Q32 — answers keep the department they were given for.
#
# There is deliberately no `retag_on_department_change`. An answer records what
# was true for the department it was asked about; a company that stops running
# Sales has not made its old Sales answers untrue, it has made them historical.
# Retagging would rewrite the past to match the present, which is the one thing
# an answer store must never do, and deleting would lose the evidence a later
# disagreement needs.
#
# `tests/test_department_answers.py` asserts this name stays `None`, so adding
# one is a deliberate act with an argument to beat rather than an oversight.
retag_on_department_change: Final[None] = None
