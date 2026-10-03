"""A Department Manager may staff their own department, and nowhere else.

D16/Q68. Managers could not invite at all before this phase; now they can, and
the interesting part is the escalation path that opening it creates.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.invitations import (
    MAX_DEPARTMENTS_PER_MEMBER,
    InvitationError,
    check_invitation,
)
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession


def _caller(role: Role, departments: set[Department]) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=frozenset(departments),
    )


FINANCE_MANAGER = _caller(Role.DEPARTMENT_MANAGER, {Department.FINANCE})


def test_a_manager_can_staff_their_own_department() -> None:
    resolved = check_invitation(
        FINANCE_MANAGER, role=Role.CONTRIBUTOR, departments=[Department.FINANCE]
    )
    assert resolved == frozenset({Department.FINANCE})


def test_a_manager_cannot_staff_another_department() -> None:
    """Refused as **"Not found"**, and that wording is deliberate.

    `departments_for` already declined a department the inviter cannot reach,
    and does so without confirming it exists — which the route turns into a 404.
    My first version raised "sales is not yours to staff": friendlier, and it
    discloses how the company is organised to somebody who was guessing. The
    existing behaviour is the better one, so this test follows it rather than
    the other way round.
    """
    with pytest.raises(InvitationError, match="Not found"):
        check_invitation(FINANCE_MANAGER, role=Role.CONTRIBUTOR, departments=[Department.SALES])


def test_a_manager_cannot_invite_above_their_own_role() -> None:
    """`outranks` still holds. Opening invitations to managers must not become a
    path to minting owners."""
    for role in (Role.OWNER, Role.EXECUTIVE):
        with pytest.raises(InvitationError, match="above your own"):
            check_invitation(FINANCE_MANAGER, role=role, departments=[Department.FINANCE])


def test_the_department_check_runs_after_the_role_derivation() -> None:
    """The escalation this ordering prevents.

    `departments_for` **derives** departments for roles that do not choose them.
    A manager inviting an Executive with no department named would pass a check
    made on the *requested* list — it is empty, so nothing is outside theirs —
    and then receive `executive` from the derivation. Checking the resolved set
    closes the gap between the two.
    """
    with pytest.raises(InvitationError):
        check_invitation(FINANCE_MANAGER, role=Role.EXECUTIVE, departments=[])


def test_nobody_can_be_put_in_more_than_three_departments() -> None:
    """Q70. Not a technical limit — a person in five departments is not really
    in any of them, and the scope lattice stops meaning anything if membership
    is how people get broad access rather than the Executive role."""
    owner = _caller(Role.OWNER, set(Department))
    too_many = [
        Department.FINANCE,
        Department.SALES,
        Department.MARKETING,
        Department.OPERATIONS,
    ]
    assert len(too_many) > MAX_DEPARTMENTS_PER_MEMBER

    with pytest.raises(InvitationError, match="at most 3 departments"):
        check_invitation(owner, role=Role.CONTRIBUTOR, departments=too_many)


def test_three_departments_is_allowed() -> None:
    owner = _caller(Role.OWNER, set(Department))
    resolved = check_invitation(
        owner,
        role=Role.CONTRIBUTOR,
        departments=[Department.FINANCE, Department.SALES, Department.MARKETING],
    )
    assert len(resolved) == MAX_DEPARTMENTS_PER_MEMBER


def test_a_contributor_still_cannot_invite_anybody() -> None:
    """Opening this to managers is one step, not a general relaxation."""
    contributor = _caller(Role.CONTRIBUTOR, {Department.FINANCE})
    with pytest.raises(InvitationError):
        check_invitation(contributor, role=Role.CONTRIBUTOR, departments=[Department.FINANCE])
