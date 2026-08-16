"""The L3 access decision.

One pure function, `decide_l3_access`, implementing ADR 0005. It lives here
rather than in each endpoint for the same reason `ROLE_GRANTS` does: a rule
spread across handlers cannot be audited, and the acceptance test would have as
many places to attack as there are routes.

**Three outcomes, not two.** The difference between `LOCKED` and `DENY` is doc
06 §4.5 in code:

- `LOCKED` — the capability exists and the caller's role does not reach it. Safe
  to say so; the UI renders "requires a manager role" and names what is gated.
  Never a `0`, which would read as "the pipeline is empty" (I10).
- `DENY` — the caller must not learn the thing exists at all. Returns nothing.

Getting those the wrong way round is how existence disclosure happens, so they
are distinct values rather than a boolean plus a message.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.scopes import Department, Scope
from app.domain.session import ScopedSession


class AccessDecision(StrEnum):
    ALLOW = "allow"
    LOCKED = "locked"
    DENY = "deny"


class Sensitivity(StrEnum):
    NORMAL = "normal"
    FINANCIAL = "financial"
    PERSONAL = "personal"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class RecordRef:
    """The metadata needed to decide access to one row — never its contents."""

    department: Department
    owner_user_id: UUID | None = None
    assignee_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    sensitivity: Sensitivity = Sensitivity.NORMAL
    is_reference_data: bool = False
    """Stages, services, price list, SOPs: how the department works, rather
    than what it is currently doing."""


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Any value computed over more than one record."""

    kind: str
    department: Department
    restricted_to_user: UUID | None = None
    """Set when the aggregate covers only one user's records. Deliberately does
    **not** grant access — see ADR 0005."""


def decide_l3_access(
    caller: ScopedSession,
    *,
    record: RecordRef | None = None,
    aggregate: Aggregate | None = None,
) -> AccessDecision:
    """Decide whether `caller` may reach this L3 record or aggregate."""
    if (record is None) == (aggregate is None):
        raise ValueError("decide_l3_access takes exactly one of record or aggregate")

    department = record.department if record is not None else aggregate.department  # type: ignore[union-attr]

    # Department first. A caller who cannot reach the department must not learn
    # anything about it, including that a capability there is gated.
    if not caller.may_reach_department(department):
        return AccessDecision.DENY

    # Then the scope ceiling. A Viewer has no L3 at all — the lattice is
    # monotonic (M1), so this is a flat denial rather than a restriction.
    if not caller.may_reach_scope(Scope.L3_DEPARTMENT):
        return AccessDecision.DENY

    if not caller.contributor_restricted:
        return AccessDecision.ALLOW

    # ── From here: an unrestricted-department Contributor ─────

    if aggregate is not None:
        # ADR 0005 rule 4. `restricted_to_user` is deliberately ignored: an
        # aggregate over only the caller's own records still leaks the
        # department total whenever the caller is the only owner, and a rule
        # that holds only while the data is large enough is not a rule.
        return AccessDecision.LOCKED

    assert record is not None

    # Rule 3 — reference data is shared, financial or not. The price list is
    # both, and withholding it would make Proposal Studio unusable.
    if record.is_reference_data:
        return AccessDecision.ALLOW

    mine = caller.user_id in {
        record.owner_user_id,
        record.assignee_user_id,
        record.created_by_user_id,
    }

    # Rules 1, 2 and 5. An unowned record is not implicitly everyone's: missing
    # metadata is a reason to withhold, the same default-deny reasoning as I4.
    if not mine:
        return AccessDecision.DENY

    # Rule 6 is already satisfied — the record is the caller's own, and you may
    # see the value of your own deal.
    return AccessDecision.ALLOW
