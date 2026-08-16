"""Scope enforcement at the API layer, not the UI.

Doc 07 M4's acceptance has two halves. `test_contributor_scope.py` covers the
rule; this covers the boundary — that the rule is applied where a client cannot
route around it, and that the HTTP mapping does not itself leak.

The mapping is the interesting part. `LOCKED` is a **200**, because it is a
rendered state rather than an error; `DENY` is a **404**, because a 403 would
mean "this exists and you may not have it".
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.deps_scope import (
    Locked,
    enforce_department,
    filter_records,
    guard_aggregate,
    guard_record,
)
from app.domain.access import Aggregate, RecordRef, Sensitivity
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession

ME = uuid4()
OTHER = uuid4()


def caller(role: Role, departments: set[Department] | None = None) -> ScopedSession:
    return ScopedSession(
        user_id=ME,
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=frozenset(departments or {Department.SALES}),
    )


# ── Departments ───────────────────────────────────────────────


def test_reaching_another_department_is_a_404_not_a_403() -> None:
    """403 says "this exists and you may not have it" — a disclosure."""
    with pytest.raises(HTTPException) as exc:
        enforce_department(caller(Role.CONTRIBUTOR, {Department.SALES}), Department.FINANCE)
    assert exc.value.status_code == 404


def test_own_department_passes() -> None:
    enforce_department(caller(Role.CONTRIBUTOR, {Department.SALES}), Department.SALES)


# ── Aggregates ────────────────────────────────────────────────


def test_a_contributor_gets_a_locked_tile_not_a_number() -> None:
    result = guard_aggregate(
        caller(Role.CONTRIBUTOR),
        Aggregate("sum", Department.SALES),
        capability="Pipeline value",
    )
    assert isinstance(result, Locked)
    assert result.capability == "Pipeline value"
    assert result.required_role == "department_manager"


def test_the_locked_payload_carries_no_value_or_count() -> None:
    """I10 and doc 06 §4.5: name the capability, disclose nothing about it."""
    result = guard_aggregate(
        caller(Role.CONTRIBUTOR), Aggregate("sum", Department.SALES), capability="Pipeline value"
    )
    assert isinstance(result, Locked)

    fields = (
        vars(result)
        if not hasattr(result, "__slots__")
        else {s: getattr(result, s) for s in result.__slots__}
    )
    for value in fields.values():
        assert not isinstance(value, (int, float)) or isinstance(value, bool), (
            f"Locked leaked a numeric field: {fields}"
        )


def test_a_manager_gets_no_lock() -> None:
    assert (
        guard_aggregate(
            caller(Role.DEPARTMENT_MANAGER),
            Aggregate("sum", Department.SALES),
            capability="Pipeline value",
        )
        is None
    )


def test_an_aggregate_in_an_unreachable_department_is_a_404() -> None:
    """Locked would confirm the department has a pipeline worth gating."""
    with pytest.raises(HTTPException) as exc:
        guard_aggregate(
            caller(Role.CONTRIBUTOR, {Department.SALES}),
            Aggregate("sum", Department.FINANCE),
            capability="Cash position",
        )
    assert exc.value.status_code == 404


def test_one_locked_tile_does_not_fail_the_response() -> None:
    """A dashboard assembles many tiles. Raising on the first gated one would
    turn a partially-locked page into an error page."""
    scope = caller(Role.CONTRIBUTOR)
    results = [
        guard_aggregate(scope, Aggregate("sum", Department.SALES), capability="Pipeline"),
        guard_aggregate(scope, Aggregate("count", Department.SALES), capability="Deal count"),
    ]
    assert all(isinstance(r, Locked) for r in results)


# ── Records ───────────────────────────────────────────────────


def test_another_persons_record_is_a_404() -> None:
    with pytest.raises(HTTPException) as exc:
        guard_record(caller(Role.CONTRIBUTOR), RecordRef(Department.SALES, owner_user_id=OTHER))
    assert exc.value.status_code == 404


def test_my_own_record_passes() -> None:
    guard_record(caller(Role.CONTRIBUTOR), RecordRef(Department.SALES, owner_user_id=ME))


# ── Lists ─────────────────────────────────────────────────────


def test_a_list_is_filtered_to_what_the_caller_may_see() -> None:
    refs = [
        RecordRef(Department.SALES, owner_user_id=ME),
        RecordRef(Department.SALES, owner_user_id=OTHER),
        RecordRef(Department.SALES, assignee_user_id=ME),
        RecordRef(Department.SALES, owner_user_id=OTHER, sensitivity=Sensitivity.FINANCIAL),
    ]
    visible = filter_records(caller(Role.CONTRIBUTOR), refs)
    assert len(visible) == 2


def test_filtering_reports_no_count_of_what_was_removed() -> None:
    """ "3 records hidden" is the disclosure doc 06 §4.5 forbids.

    Asserted on the signature: the function returns a list, not a list plus a
    total, so there is nothing for a caller to render.
    """
    refs = [RecordRef(Department.SALES, owner_user_id=OTHER) for _ in range(5)]
    visible = filter_records(caller(Role.CONTRIBUTOR), refs)
    assert visible == []
    assert isinstance(visible, list)


def test_a_manager_sees_the_whole_list() -> None:
    refs = [
        RecordRef(Department.SALES, owner_user_id=ME),
        RecordRef(Department.SALES, owner_user_id=OTHER),
    ]
    assert len(filter_records(caller(Role.DEPARTMENT_MANAGER), refs)) == 2


def test_a_viewer_sees_no_l3_records_at_all() -> None:
    refs = [RecordRef(Department.SALES, owner_user_id=ME)]
    assert filter_records(caller(Role.VIEWER), refs) == []
