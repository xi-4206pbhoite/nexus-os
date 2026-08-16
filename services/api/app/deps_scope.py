"""Scope enforcement at the API layer.

Doc 07 M4: *"the role → scope table is enforced at the API layer"* — not in the
UI. A hidden button is a presentation choice; this is the boundary.

The helpers here turn an `AccessDecision` into an HTTP response, and the mapping
is the whole point:

| Decision | HTTP | What the caller learns |
|---|---|---|
| `ALLOW` | the data | — |
| `LOCKED` | **200** + a Locked payload | the capability exists and their role does not reach it |
| `DENY` | **404** | nothing |

`LOCKED` is deliberately a success, not a 403. It is a *rendered state* — the
tile says "requires a manager role" and names what is gated (doc 06 §4.5, I10).
A 403 would push the UI into an error path and tempt it to show `0`.

`DENY` is 404 rather than 403 for the opposite reason: 403 means "this exists
and you may not have it", which is an existence disclosure. 404 says nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from app.domain.access import AccessDecision, Aggregate, RecordRef, decide_l3_access
from app.domain.scopes import Department
from app.domain.session import ScopedSession


@dataclass(frozen=True, slots=True)
class Locked:
    """A capability the caller's role does not reach.

    Rendered, never raised. Carries no value and no count — doc 06 §4.5 permits
    naming the capability and the requirement, nothing else.
    """

    capability: str
    required_role: str
    reason: str
    state: str = "locked"


def enforce_department(caller: ScopedSession, department: Department) -> None:
    """404 if the caller cannot reach this department at all."""
    if not caller.may_reach_department(department):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def guard_aggregate(
    caller: ScopedSession, aggregate: Aggregate, *, capability: str
) -> Locked | None:
    """Return `Locked` to render, or `None` when the caller may compute it.

    Returning rather than raising is deliberate: a dashboard assembles many
    tiles, and one gated tile must not fail the whole response.
    """
    decision = decide_l3_access(caller, aggregate=aggregate)
    if decision is AccessDecision.ALLOW:
        return None
    if decision is AccessDecision.LOCKED:
        return Locked(
            capability=capability,
            required_role="department_manager",
            reason="Department totals are available to managers and above.",
        )
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def guard_record(caller: ScopedSession, ref: RecordRef) -> None:
    """404 unless the caller may reach this record.

    Raises rather than returns: a single record either is the response or is
    not. There is no partial rendering of a row the caller cannot see.
    """
    if decide_l3_access(caller, record=ref) is not AccessDecision.ALLOW:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def filter_records(caller: ScopedSession, refs: list[RecordRef]) -> list[RecordRef]:
    """Drop what the caller cannot reach.

    Note the return shape: a filtered list, with **no count of what was
    removed**. "3 records hidden" is precisely the disclosure doc 06 §4.5
    forbids.
    """
    return [r for r in refs if decide_l3_access(caller, record=r) is AccessDecision.ALLOW]
