"""What a Contributor may reach inside L3 (ADR 0005).

Doc 07 M4's acceptance: **"a Contributor cannot reach L3 aggregates."** This
file is that assertion, attacked from every angle I could construct.

The failure this guards against is not dramatic. It is a junior hire who can
read the whole department's numbers because nobody defined what "restricted"
meant — doc 06 §2.3's correction that *Contributor is not a junior Manager*.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.domain.access import (
    AccessDecision,
    Aggregate,
    RecordRef,
    Sensitivity,
    decide_l3_access,
)
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession

TENANT = uuid4()
WORKSPACE = uuid4()
ME = uuid4()
SOMEONE_ELSE = uuid4()


def caller(role: Role, departments: set[Department] | None = None) -> ScopedSession:
    return ScopedSession(
        user_id=ME,
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        role=role,
        departments=frozenset(departments or {Department.SALES}),
    )


def record(
    *,
    owner: UUID | None = None,
    assignee: UUID | None = None,
    created_by: UUID | None = None,
    department: Department = Department.SALES,
    sensitivity: Sensitivity = Sensitivity.NORMAL,
    reference_data: bool = False,
) -> RecordRef:
    return RecordRef(
        department=department,
        owner_user_id=owner,
        assignee_user_id=assignee,
        created_by_user_id=created_by,
        sensitivity=sensitivity,
        is_reference_data=reference_data,
    )


CONTRIBUTOR = Role.CONTRIBUTOR
MANAGER = Role.DEPARTMENT_MANAGER


# ── Rule 4: aggregates are denied ─────────────────────────────


@pytest.mark.parametrize(
    "kind",
    ["sum", "count", "avg", "min", "max", "percentile", "forecast", "score"],
)
def test_contributor_cannot_reach_any_aggregate(kind: str) -> None:
    decision = decide_l3_access(
        caller(CONTRIBUTOR), aggregate=Aggregate(kind=kind, department=Department.SALES)
    )
    assert decision is AccessDecision.LOCKED, f"{kind} aggregate reached a Contributor"


def test_a_manager_reaches_the_same_aggregate() -> None:
    """The restriction is Contributor-specific, not a department-wide blackout."""
    decision = decide_l3_access(
        caller(MANAGER), aggregate=Aggregate(kind="sum", department=Department.SALES)
    )
    assert decision is AccessDecision.ALLOW


def test_an_aggregate_over_only_my_own_records_is_still_denied() -> None:
    """Otherwise the boundary depends on how many records happen to exist.

    A Contributor who is currently the only owner in the department could read
    the department total by inference. A rule that holds only while the data is
    large enough is not a rule.
    """
    decision = decide_l3_access(
        caller(CONTRIBUTOR),
        aggregate=Aggregate(kind="sum", department=Department.SALES, restricted_to_user=ME),
    )
    assert decision is AccessDecision.LOCKED


def test_aggregates_in_another_department_are_denied_outright() -> None:
    """Not Locked — a Contributor has no business knowing Finance's shape.

    Doc 06 §4.5: a capability being gated is disclosable; the contents of a
    department the caller cannot reach are not.
    """
    decision = decide_l3_access(
        caller(CONTRIBUTOR, {Department.SALES}),
        aggregate=Aggregate(kind="sum", department=Department.FINANCE),
    )
    assert decision is AccessDecision.DENY


# ── Rules 1 & 2: own records are reachable ────────────────────


def test_contributor_reaches_a_record_they_own() -> None:
    assert decide_l3_access(caller(CONTRIBUTOR), record=record(owner=ME)) is AccessDecision.ALLOW


def test_contributor_reaches_a_record_assigned_to_them() -> None:
    assert decide_l3_access(caller(CONTRIBUTOR), record=record(assignee=ME)) is AccessDecision.ALLOW


def test_contributor_reaches_a_record_they_created() -> None:
    assert (
        decide_l3_access(caller(CONTRIBUTOR), record=record(created_by=ME)) is AccessDecision.ALLOW
    )


# ── Rule 5: other people's records are not ────────────────────


def test_contributor_cannot_reach_another_persons_record() -> None:
    """Same department, same scope level — still not theirs."""
    decision = decide_l3_access(caller(CONTRIBUTOR), record=record(owner=SOMEONE_ELSE))
    assert decision is AccessDecision.DENY


def test_a_manager_reaches_their_departments_records() -> None:
    decision = decide_l3_access(caller(MANAGER), record=record(owner=SOMEONE_ELSE))
    assert decision is AccessDecision.ALLOW


def test_an_unowned_record_is_not_implicitly_everyones() -> None:
    """A record with no owner must not default to visible.

    I4's default-deny reasoning applied to the relational path: missing
    metadata is a reason to withhold, not to share.
    """
    decision = decide_l3_access(caller(CONTRIBUTOR), record=record())
    assert decision is AccessDecision.DENY


# ── Rule 3: reference data is shared ──────────────────────────


def test_contributor_reaches_department_reference_data() -> None:
    """Stages, services, price list — how the department works, not what it is
    currently doing. Without this a Contributor cannot do their job."""
    decision = decide_l3_access(
        caller(CONTRIBUTOR), record=record(reference_data=True, owner=SOMEONE_ELSE)
    )
    assert decision is AccessDecision.ALLOW


def test_reference_data_in_another_department_is_still_denied() -> None:
    decision = decide_l3_access(
        caller(CONTRIBUTOR, {Department.SALES}),
        record=record(reference_data=True, department=Department.FINANCE),
    )
    assert decision is AccessDecision.DENY


# ── Rule 6: financial fields on others' records ───────────────


def test_financial_sensitivity_on_someone_elses_record_is_denied() -> None:
    decision = decide_l3_access(
        caller(CONTRIBUTOR),
        record=record(owner=SOMEONE_ELSE, sensitivity=Sensitivity.FINANCIAL),
    )
    assert decision is AccessDecision.DENY


def test_financial_sensitivity_on_my_own_record_is_allowed() -> None:
    """You may see the value of your own deal."""
    decision = decide_l3_access(
        caller(CONTRIBUTOR), record=record(owner=ME, sensitivity=Sensitivity.FINANCIAL)
    )
    assert decision is AccessDecision.ALLOW


def test_financial_reference_data_is_still_reachable() -> None:
    """The price list is financial *and* reference data — it is how the job is
    done, and withholding it would make Proposal Studio unusable."""
    decision = decide_l3_access(
        caller(CONTRIBUTOR),
        record=record(reference_data=True, sensitivity=Sensitivity.FINANCIAL),
    )
    assert decision is AccessDecision.ALLOW


# ── Roles other than Contributor ──────────────────────────────


def test_a_viewer_reaches_no_l3_at_all() -> None:
    """Monotonic lattice (M1): a Viewer has no L3, restricted or otherwise."""
    assert decide_l3_access(caller(Role.VIEWER), record=record(owner=ME)) is AccessDecision.DENY
    assert (
        decide_l3_access(caller(Role.VIEWER), aggregate=Aggregate("sum", Department.SALES))
        is AccessDecision.DENY
    )


def test_an_owner_reaches_every_department() -> None:
    for department in Department:
        assert (
            decide_l3_access(caller(Role.OWNER), aggregate=Aggregate("sum", department))
            is AccessDecision.ALLOW
        )


def test_external_reaches_nothing() -> None:
    assert decide_l3_access(caller(Role.EXTERNAL), record=record(owner=ME)) is AccessDecision.DENY


# ── Shape of the rule ─────────────────────────────────────────


def test_a_request_must_be_one_thing_or_the_other() -> None:
    """Neither a record nor an aggregate is a programming error, not a default
    allow."""
    with pytest.raises(ValueError):
        decide_l3_access(caller(CONTRIBUTOR))


def test_locked_is_distinguishable_from_denied() -> None:
    """I10 and doc 06 §4.5 depend on the difference.

    LOCKED renders "requires a manager role" and names the capability. DENY
    returns nothing at all — the caller must not learn the thing exists.
    """
    assert AccessDecision.LOCKED is not AccessDecision.DENY
    assert AccessDecision.LOCKED is not AccessDecision.ALLOW
