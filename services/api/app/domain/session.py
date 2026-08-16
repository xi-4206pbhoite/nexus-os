"""`ScopedSession` — the caller's resolved authority for one request.

**I2: identity is bound to the session, never passed as a tool argument.**

Everything that reads data takes one of these. It is constructed server-side
from the session cookie and the membership row; it is never built from a client
value, and it never appears in a model context. A retrieval tool takes a query;
it does not take a `user_id`, because a model whose context contains a crawled
competitor page would then be one injected line away from requesting another
user's scope (doc 06 §4.3).

`workspace_id` is resolved per request from the server-side session, never from
a header or body field. Doc 06 §2.1 is explicit that a workspace switcher breaks
the "one tenant per session" assumption that claim-based RLS relies on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from app.domain.scopes import Department, Role, Scope, grant_for


@dataclass(frozen=True, slots=True)
class ScopedSession:
    user_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    role: Role
    departments: frozenset[Department] = field(default_factory=frozenset)
    named_l4_item_ids: frozenset[UUID] = field(default_factory=frozenset)

    # ── Derived authority ─────────────────────────────────────

    @property
    def max_scope(self) -> Scope | None:
        return grant_for(self.role).max_scope

    @property
    def contributor_restricted(self) -> bool:
        return grant_for(self.role).contributor_restricted

    @property
    def can_see_executive_surface(self) -> bool:
        return grant_for(self.role).executive_surface

    @property
    def has_all_departments(self) -> bool:
        return grant_for(self.role).all_departments

    # ── Decisions ─────────────────────────────────────────────

    def may_reach_scope(self, scope: Scope) -> bool:
        """Whether this caller may reach a given scope *by role alone*.

        L4 is deliberately excluded: it is reachable only by being named on the
        specific item, which `may_reach_l4_item` decides. Answering `True` here
        for an Owner would make L4 a UI convention rather than a boundary.
        """
        ceiling = self.max_scope
        if ceiling is None:
            return False
        if scope is Scope.L4_RESTRICTED:
            return False
        if scope is Scope.L5_PERSONAL:
            # Own personal content only; ownership is checked at the row.
            return True
        return scope <= ceiling

    def may_reach_department(self, department: Department) -> bool:
        if self.max_scope is None:
            return False
        if self.has_all_departments:
            return True
        return department in self.departments

    def may_reach_l4_item(self, item_id: UUID) -> bool:
        """L4 is reachable only by being named on the item — Owner included."""
        return item_id in self.named_l4_item_ids

    def may_reach_l5_item(self, owner_user_id: UUID) -> bool:
        return owner_user_id == self.user_id

    # ── Cache key (I5) ────────────────────────────────────────

    def cache_key(self) -> str:
        """Identity of the caller's *authority*, for permission-keyed caching.

        I5 requires every cached or precomputed artifact — generations, health
        scores, `score_history`, scheduled briefs — to be keyed by the
        requesting principal's resolved scope set, not by tenant. Without this,
        an Owner-triggered composite is served to a Contributor and "role
        changes take effect immediately" is false for every cached surface
        (doc 06 §4.9).

        Deliberately *not* keyed on `user_id`: two callers with identical
        authority should share a cache entry. Including the user id would be
        safe but would defeat the cache for no security gain. L4 named items are
        included because they genuinely change what is visible.
        """
        parts = [
            str(self.workspace_id),
            self.role.value,
            ",".join(sorted(d.value for d in self.departments)),
            ",".join(sorted(str(i) for i in self.named_l4_item_ids)),
        ]
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
        return f"scope:{digest}"
