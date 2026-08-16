"""The role → scope table from doc 06 §2.3, asserted row by row.

This table is the security model. Doc 07 §5.3 requires the test that proves an
invariant to be written before the feature it guards, and doc 07 M1's acceptance
is that the mapping is enforced "as data, not scattered conditionals" — so it is
tested as a table too.

Each of the three corrections doc 06 records has its own test, because each was
a real defect in an earlier version of the model and a regression would be
silent.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.scopes import Department, Role, Scope, grant_for
from app.domain.session import ScopedSession

TENANT = uuid4()
WORKSPACE = uuid4()


def session_for(
    role: Role,
    departments: set[Department] | None = None,
    named_l4: set[str] | None = None,
) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        role=role,
        departments=frozenset(departments or set()),
        named_l4_item_ids=frozenset(),
    )


# ── The table itself ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "l1", "l2", "l3"),
    [
        (Role.OWNER, True, True, True),
        (Role.EXECUTIVE, True, True, True),
        (Role.DEPARTMENT_MANAGER, True, True, True),
        (Role.CONTRIBUTOR, True, True, True),
        (Role.VIEWER, True, True, False),
        (Role.EXTERNAL, False, False, False),
    ],
)
def test_scope_ceiling_matches_doc_06_table(role: Role, l1: bool, l2: bool, l3: bool) -> None:
    s = session_for(role, {Department.SALES})
    assert s.may_reach_scope(Scope.L1_COMPANY_PUBLIC) is l1
    assert s.may_reach_scope(Scope.L2_COMPANY_INTERNAL) is l2
    assert s.may_reach_scope(Scope.L3_DEPARTMENT) is l3


# ── Correction 1: the lattice is monotonic ────────────────────


@pytest.mark.parametrize("role", list(Role))
def test_lattice_is_monotonic(role: Role) -> None:
    """No role may reach a higher scope while being denied a lower one.

    A Viewer previously reached L3 department detail while being denied
    less-sensitive L2. That is not a lattice, and any rule built on it is
    unsound.
    """
    s = session_for(role, {Department.SALES})
    reachable = [
        s.may_reach_scope(sc)
        for sc in (Scope.L1_COMPANY_PUBLIC, Scope.L2_COMPANY_INTERNAL, Scope.L3_DEPARTMENT)
    ]
    # Once False, must stay False as sensitivity rises.
    assert reachable == sorted(reachable, reverse=True), (
        f"{role} has a hole in the lattice: {reachable}"
    )


def test_viewer_gets_no_l3_at_all() -> None:
    viewer = session_for(Role.VIEWER, {Department.SALES})
    assert viewer.may_reach_scope(Scope.L2_COMPANY_INTERNAL) is True
    assert viewer.may_reach_scope(Scope.L3_DEPARTMENT) is False


# ── Correction 2: Contributor is not Manager ──────────────────


def test_contributor_l3_is_restricted_and_manager_l3_is_not() -> None:
    """A junior salesperson must not hold every deal value in the pipeline."""
    contributor = session_for(Role.CONTRIBUTOR, {Department.SALES})
    manager = session_for(Role.DEPARTMENT_MANAGER, {Department.SALES})

    assert contributor.may_reach_scope(Scope.L3_DEPARTMENT) is True
    assert contributor.contributor_restricted is True

    assert manager.may_reach_scope(Scope.L3_DEPARTMENT) is True
    assert manager.contributor_restricted is False


# ── Correction 3: L4 is not reachable by role ─────────────────


@pytest.mark.parametrize("role", list(Role))
def test_l4_is_never_reachable_by_role_alone(role: Role) -> None:
    """Including Owner. Otherwise L4 is a UI convention, not a boundary."""
    s = session_for(role, set(Department))
    assert s.may_reach_scope(Scope.L4_RESTRICTED) is False


def test_l4_is_reachable_only_by_being_named() -> None:
    item = uuid4()
    other = uuid4()

    named = ScopedSession(
        user_id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        role=Role.CONTRIBUTOR,
        departments=frozenset({Department.HR}),
        named_l4_item_ids=frozenset({item}),
    )
    assert named.may_reach_l4_item(item) is True
    assert named.may_reach_l4_item(other) is False

    owner = session_for(Role.OWNER, set(Department))
    assert owner.may_reach_l4_item(item) is False


# ── Departments ───────────────────────────────────────────────


def test_department_manager_reaches_only_its_own_department() -> None:
    s = session_for(Role.DEPARTMENT_MANAGER, {Department.SALES})
    assert s.may_reach_department(Department.SALES) is True
    assert s.may_reach_department(Department.FINANCE) is False


def test_owner_and_executive_reach_every_department() -> None:
    for role in (Role.OWNER, Role.EXECUTIVE):
        s = session_for(role)
        for dept in Department:
            assert s.may_reach_department(dept) is True, f"{role} denied {dept}"


def test_external_reaches_nothing() -> None:
    s = session_for(Role.EXTERNAL, set(Department))
    for dept in Department:
        assert s.may_reach_department(dept) is False
    for scope in Scope:
        assert s.may_reach_scope(scope) is False


# ── L5 ────────────────────────────────────────────────────────


def test_l5_is_own_content_only() -> None:
    s = session_for(Role.OWNER, set(Department))
    assert s.may_reach_l5_item(s.user_id) is True
    assert s.may_reach_l5_item(uuid4()) is False


# ── Executive surface (doc 06 §2.4) ───────────────────────────


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (Role.OWNER, True),
        (Role.EXECUTIVE, True),
        (Role.DEPARTMENT_MANAGER, False),
        (Role.CONTRIBUTOR, False),
        (Role.VIEWER, False),
        (Role.EXTERNAL, False),
    ],
)
def test_executive_surface_is_owner_and_executive_only(role: Role, expected: bool) -> None:
    """Doc 06 §2.4 — a Department Manager's portal is six directors, not seven.

    This contradicts doc 05 §1's "seven equal directors" for every non-executive
    user. Doc 06 records the contradiction and recommends the restriction; the
    test exists so the choice is explicit rather than incidental.
    """
    assert session_for(role).can_see_executive_surface is expected


# ── The table is complete ─────────────────────────────────────


def test_every_role_has_a_grant() -> None:
    """A role without a row would fall through to a KeyError at request time."""
    for role in Role:
        assert grant_for(role) is not None
