"""I5 — caches and precomputed artifacts are keyed by resolved scope set.

Doc 06 §4.9: any cached or precomputed artifact — generations, composite
scores, `score_history` rows, nightly briefs — is keyed by the requesting
principal's resolved scope set, **not by tenant alone**. Without this, an
Owner-triggered composite is served to a Contributor, and "role changes take
effect immediately" is false for every cached surface.

These tests are the guard. They are written now, before any cache exists, so
that the first cache added cannot key on the wrong thing.
"""

from __future__ import annotations

from uuid import uuid4

from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession

TENANT = uuid4()
WORKSPACE_A = uuid4()
WORKSPACE_B = uuid4()


def make(
    *,
    role: Role = Role.CONTRIBUTOR,
    workspace=WORKSPACE_A,
    departments: set[Department] | None = None,
    named_l4: set | None = None,
    user_id=None,
) -> ScopedSession:
    return ScopedSession(
        user_id=user_id or uuid4(),
        tenant_id=TENANT,
        workspace_id=workspace,
        role=role,
        departments=frozenset(departments or {Department.SALES}),
        named_l4_item_ids=frozenset(named_l4 or set()),
    )


def test_different_roles_never_share_a_cache_entry() -> None:
    """The core of I5: an Owner's composite must not be served to a Viewer."""
    owner = make(role=Role.OWNER)
    viewer = make(role=Role.VIEWER)
    assert owner.cache_key() != viewer.cache_key()


def test_different_departments_never_share_a_cache_entry() -> None:
    sales = make(departments={Department.SALES})
    finance = make(departments={Department.FINANCE})
    assert sales.cache_key() != finance.cache_key()


def test_different_workspaces_never_share_a_cache_entry() -> None:
    """Doc 06 §2.1 — every cache key includes workspace.

    A workspace switcher breaks the one-tenant-per-session assumption, so a
    key that omits workspace serves one client's agency data to another.
    """
    a = make(workspace=WORKSPACE_A)
    b = make(workspace=WORKSPACE_B)
    assert a.cache_key() != b.cache_key()


def test_named_l4_items_change_the_key() -> None:
    """Being named on an L4 item genuinely changes what is visible."""
    item = uuid4()
    without = make()
    with_item = make(named_l4={item})
    assert without.cache_key() != with_item.cache_key()


def test_identical_authority_shares_a_cache_entry() -> None:
    """Two callers with the same authority should hit the same entry.

    Keying on user_id would be safe but would defeat the cache for no security
    gain — every Sales contributor would recompute the same department view.
    """
    a = make(role=Role.CONTRIBUTOR, departments={Department.SALES})
    b = make(role=Role.CONTRIBUTOR, departments={Department.SALES})
    assert a.user_id != b.user_id
    assert a.cache_key() == b.cache_key()


def test_department_order_does_not_change_the_key() -> None:
    """Set ordering must not fragment the cache."""
    a = make(departments={Department.SALES, Department.FINANCE})
    b = make(departments={Department.FINANCE, Department.SALES})
    assert a.cache_key() == b.cache_key()


def test_key_does_not_leak_identifiers() -> None:
    """Cache keys reach logs and metrics; they should not carry raw ids."""
    s = make(role=Role.OWNER, departments={Department.FINANCE})
    key = s.cache_key()
    assert str(s.workspace_id) not in key
    assert str(s.user_id) not in key
    assert key.startswith("scope:")
