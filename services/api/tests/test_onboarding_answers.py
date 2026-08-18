"""The answer route's decisions: who may write, what may be written, and where.

`test_onboarding_scope.py` proves the catalogue is classified. This proves the
route honours that classification instead of taking the client's word for it,
and it is deliberately hermetic — every assertion here is about a decision, and
none of them needs a database to be wrong.

Three properties, each of which has a specific failure behind it:

- **Scope comes from the catalogue.** A request that could name its own scope
  could store an average deal size as L1 and hand it to every Viewer.
- **Answering is not authorising.** Doc 06 §2.2 — a role you type into a form
  must not become a role you hold.
- **Brief recipients are workspace users.** Doc 06 §4.10, and the reason the
  question sits in a stage after invitation at all.
"""

from __future__ import annotations

import inspect
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.domain.onboarding import BY_KEY, CATALOGUE, AnswerType, scope_for_answer
from app.domain.scopes import Department, Role, Scope
from app.domain.session import ScopedSession
from app.routes import setup as setup_routes
from app.routes.setup import (
    AcceptIn,
    AnswerIn,
    ensure_may_answer,
    may_read_answer,
    validate_answer,
)

MEMBER = UUID("11111111-1111-1111-1111-111111111111")
STRANGER = UUID("99999999-9999-9999-9999-999999999999")
MEMBERS = frozenset({MEMBER})


def caller(role: Role, departments: set[Department] | None = None) -> ScopedSession:
    return ScopedSession(
        user_id=MEMBER,
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=frozenset(departments or {Department.SALES}),
    )


def check(key: str, value: Any, *, members: frozenset[UUID] = MEMBERS) -> Any:
    return validate_answer(BY_KEY[key], value, member_ids=members)


# ── Scope is never taken from the request ─────────────────────


def test_an_answer_carries_only_a_key_and_a_value() -> None:
    """The wire model has nowhere to put a scope, so nothing can spoof one.

    This is the structural version of doc 06 §2.5. A `scope` field here would be
    the whole vulnerability: the classification would arrive from the same place
    as the data it classifies.
    """
    assert set(AnswerIn.model_fields) == {"key", "value"}


def test_the_route_never_reads_a_scope_from_the_payload() -> None:
    """Belt and braces on the model test: the source must not reach for one."""
    source = inspect.getsource(setup_routes)
    for forbidden in ("answer.scope", "payload.scope", "answer.department"):
        assert forbidden not in source, f"the route reads {forbidden} from the request"


def test_every_catalogue_key_resolves_to_a_classification() -> None:
    """The route looks each key up rather than defaulting; an unknown one raises."""
    for question in CATALOGUE:
        scope, department = scope_for_answer(question.key)
        assert scope is question.scope
        assert department is question.department


# ── Who may write ─────────────────────────────────────────────


@pytest.mark.parametrize("role", [Role.OWNER, Role.EXECUTIVE])
def test_an_administrator_may_answer(role: Role) -> None:
    ensure_may_answer(caller(role), BY_KEY["stated_purpose"])


@pytest.mark.parametrize(
    "role", [Role.DEPARTMENT_MANAGER, Role.CONTRIBUTOR, Role.VIEWER, Role.EXTERNAL]
)
def test_everyone_else_is_refused(role: Role) -> None:
    """D16 is open, so this is the default-deny reading (I4) rather than a
    settled one. It is asserted so that widening it is a deliberate act."""
    with pytest.raises(HTTPException) as exc:
        ensure_may_answer(caller(role), BY_KEY["stated_purpose"])
    assert exc.value.status_code == 403


def test_a_viewer_cannot_write_a_company_fact_they_can_read() -> None:
    """Reading L2 and configuring the workspace are different privileges.

    A Viewer reaches L2, so a check built only from `may_reach_scope` would let
    one overwrite the company's stated purpose for everybody.
    """
    viewer = caller(Role.VIEWER)
    assert may_read_answer(viewer, Scope.L2_COMPANY_INTERNAL, None)
    with pytest.raises(HTTPException):
        ensure_may_answer(viewer, BY_KEY["stated_purpose"])


# ── The second layer, which the first currently hides ─────────


def test_a_manager_cannot_read_another_departments_answer() -> None:
    """The per-answer check, exercised directly.

    Unreachable through `ensure_may_answer` while only Owner and Executive get
    past the administration gate — and this is the check that has to already be
    there if D16 ever admits Department Managers, which is D15's second open
    question in one line.
    """
    sales_manager = caller(Role.DEPARTMENT_MANAGER, {Department.SALES})
    assert not may_read_answer(sales_manager, Scope.L3_DEPARTMENT, Department.FINANCE)
    assert may_read_answer(sales_manager, Scope.L3_DEPARTMENT, Department.SALES)


def test_a_contributor_cannot_read_their_own_departments_money_answer() -> None:
    """ADR 0005: an onboarding money figure is a department-wide fact, so it is
    decided as an aggregate — Locked for a Contributor, not visible."""
    contributor = caller(Role.CONTRIBUTOR, {Department.SALES})
    assert not may_read_answer(contributor, Scope.L3_DEPARTMENT, Department.SALES)


def test_an_l3_answer_with_no_department_is_withheld() -> None:
    """A CHECK constraint forbids storing this. If one is ever read anyway,
    withhold it rather than guess a department (I4)."""
    assert not may_read_answer(caller(Role.OWNER), Scope.L3_DEPARTMENT, None)


# ── Values ────────────────────────────────────────────────────


def test_a_closed_question_refuses_an_answer_off_the_list() -> None:
    assert check("currency", "INR") == "INR"
    with pytest.raises(HTTPException) as exc:
        check("currency", "BITCOIN")
    assert exc.value.status_code == 400


def test_the_role_question_offers_the_roles_the_security_model_knows() -> None:
    """Its options come from the enum, so the two cannot drift apart."""
    offered = {c.value for c in BY_KEY["role"].options}
    assert offered == {r.value for r in Role}


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "1200", None])
def test_money_refuses_anything_that_is_not_a_number(bad: Any) -> None:
    """`True` is in that list on purpose: `isinstance(True, int)` is True in
    Python, so a bare numeric check would store a boolean as a deal size."""
    with pytest.raises(HTTPException):
        check("average_deal_size", bad)


def test_money_accepts_a_figure() -> None:
    assert check("average_deal_size", 12500) == 12500.0


def test_a_url_without_a_scheme_is_accepted_and_normalised() -> None:
    assert check("company_url", "acme.example") == "https://acme.example"


@pytest.mark.parametrize("bad", ["not a url", "javascript:alert(1)", "  "])
def test_a_url_that_is_not_one_is_refused(bad: str) -> None:
    with pytest.raises(HTTPException):
        check("company_url", bad)


def test_a_free_entry_list_keeps_the_order_it_was_given() -> None:
    """`ranked_goals` is a ranking. Sorting or de-ordering it silently would
    store a different answer than the one the person gave."""
    assert check("ranked_goals", ["retention", "new logos", "margin"]) == [
        "retention",
        "new logos",
        "margin",
    ]


def test_a_repeated_entry_is_dropped_without_disturbing_the_rest() -> None:
    assert check("forbidden_terms", ["synergy", "leverage", "synergy"]) == [
        "synergy",
        "leverage",
    ]


def test_an_over_long_list_is_refused() -> None:
    with pytest.raises(HTTPException):
        check("biggest_challenges", [f"challenge {n}" for n in range(200)])


# ── Brief recipients (doc 06 §4.10) ───────────────────────────


def test_brief_recipients_accepts_a_workspace_member() -> None:
    assert check("brief_recipients", [str(MEMBER)]) == [str(MEMBER)]


def test_brief_recipients_refuses_somebody_who_is_not_in_the_workspace() -> None:
    """The rule that made this a post-invitation question: you cannot pick a
    recipient from a list that does not exist yet."""
    with pytest.raises(HTTPException) as exc:
        check("brief_recipients", [str(STRANGER)])
    assert exc.value.status_code == 400


def test_brief_recipients_refuses_a_free_text_address() -> None:
    """Doc 06 §4.10 — recipients are workspace users, never typed addresses.
    The brief is a cross-department composite that cannot be recalled."""
    with pytest.raises(HTTPException):
        check("brief_recipients", ["someone@example.com"])


def test_the_only_user_list_question_is_the_recipients_one() -> None:
    """If a second one appears, it inherits this membership check by type —
    which is the reason the check is on the type rather than on the key."""
    keys = {q.key for q in CATALOGUE if q.answer_type is AnswerType.USER_LIST}
    assert keys == {"brief_recipients"}


# ── Acceptance supplies nothing (doc 06 §2.2) ─────────────────


def test_accepting_an_invitation_takes_a_token_and_nothing_else() -> None:
    """*"Self-declared role is privilege escalation via dropdown."* There is no
    dropdown, because there is no field."""
    assert set(AcceptIn.model_fields) == {"token"}
