"""Two invariants: a field resolves against the caller, an artifact inherits max().

P19 and P21. Both are about the same failure — a value that is correct for one
reader appearing in front of another — arriving by two different routes.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.artifacts import Artifact, declassify, mark_stale
from app.domain.field_scope import redact, visible_fields
from app.domain.scopes import Department, Role, Scope
from app.domain.session import ScopedSession

PROJECT = {
    "name": "Muscat fit-out",
    "milestones": ["a", "b"],
    "progress": 0.4,
    "cost_lines": [1000, 2000],
    "margin": 0.22,
}


def _caller(role: Role, departments: set[Department]) -> ScopedSession:
    return ScopedSession(
        user_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        departments=frozenset(departments),
    )


def test_a_supervisor_sees_the_project_and_not_the_margin() -> None:
    """P19's sentence, as a test. The same row, two readers, two answers."""
    supervisor = _caller(Role.CONTRIBUTOR, {Department.OPERATIONS})
    seen = redact(PROJECT, supervisor)

    assert "name" in seen and "milestones" in seen
    assert "margin" not in seen
    assert "cost_lines" not in seen


def test_a_hidden_field_is_omitted_not_nulled() -> None:
    """`margin: null` beside a populated project tells the reader a margin
    exists and is being withheld — a disclosure about the company's structure,
    and an invitation to go looking elsewhere."""
    seen = redact(PROJECT, _caller(Role.CONTRIBUTOR, {Department.OPERATIONS}))
    assert "margin" not in seen.keys()


def test_finance_sees_the_cost_lines() -> None:
    finance = _caller(Role.DEPARTMENT_MANAGER, {Department.FINANCE})
    assert "cost_lines" in visible_fields(finance)


def test_visible_fields_returns_names_so_the_query_can_use_them() -> None:
    """Filtering after the fetch means the hidden value was already loaded into
    a process that serialises objects for a living, and the only thing between
    it and the response is a `del`."""
    assert isinstance(visible_fields(_caller(Role.OWNER, set(Department))), frozenset)


# ── Artifacts (I6) ────────────────────────────────────────────


def _artifact(*scopes: Scope, facts: tuple[str, ...] = ()) -> Artifact:
    return Artifact(id=uuid4(), version=1, input_scopes=scopes, input_fact_keys=facts)


def test_one_restricted_input_governs_the_whole_artifact() -> None:
    """A summary of one L4 figure and twenty L2 ones is L4. The restricted
    number is *in* it, and averaging the scopes would produce a document that
    reads as shareable and is not."""
    mixed = _artifact(*([Scope.L2_COMPANY_INTERNAL] * 20), Scope.L4_RESTRICTED)
    assert mixed.inherited_scope is Scope.L4_RESTRICTED
    assert mixed.needs_confirmation_to_share


def test_an_artifact_built_from_nothing_is_restricted_not_public() -> None:
    """The safe reading of "we cannot tell where this came from" is the most
    restrictive one. The opposite default would let a bug in input tracking
    silently publish something."""
    assert _artifact().inherited_scope is Scope.L5_PERSONAL


def test_declassifying_without_a_reason_is_refused() -> None:
    """ "Who decided this could be shared, and why" is the first question asked
    afterwards."""
    with pytest.raises(ValueError, match="needs a reason"):
        declassify(
            _artifact(Scope.L4_RESTRICTED),
            to=Scope.L2_COMPANY_INTERNAL,
            by_user_id=uuid4(),
            reason="  ",
        )


def test_declassifying_only_ever_loosens() -> None:
    """Tightening is not declassification, and an artifact quietly becoming more
    restricted breaks links for people who already hold it."""
    with pytest.raises(ValueError, match="only ever loosens"):
        declassify(
            _artifact(Scope.L2_COMPANY_INTERNAL),
            to=Scope.L4_RESTRICTED,
            by_user_id=uuid4(),
            reason="tightening",
        )


def test_a_declassified_artifact_records_who_and_why() -> None:
    who = uuid4()
    result = declassify(
        _artifact(Scope.L4_RESTRICTED),
        to=Scope.L2_COMPANY_INTERNAL,
        by_user_id=who,
        reason="Client-facing summary, figures removed.",
    )
    assert result.effective_scope is Scope.L2_COMPANY_INTERNAL
    assert result.declassified_by_user_id == who
    assert result.declassified_reason
    assert not result.needs_confirmation_to_share


def test_a_changed_fact_marks_stale_rather_than_regenerating() -> None:
    """Somebody may have sent this to a client, and the version they hold has to
    go on existing. Regenerating in place changes a document after it was
    quoted, which is worse than an out-of-date one that admits it."""
    original = _artifact(Scope.L2_COMPANY_INTERNAL, facts=("revenue",))
    marked = mark_stale(original, changed_fact="revenue")

    assert marked.stale
    assert marked.version == original.version, "the version is not bumped; it is flagged"


def test_an_unrelated_fact_does_not_mark_it_stale() -> None:
    original = _artifact(Scope.L2_COMPANY_INTERNAL, facts=("revenue",))
    assert not mark_stale(original, changed_fact="headcount").stale
