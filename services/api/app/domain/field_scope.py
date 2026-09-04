"""Cross-department fields resolve at read time, against the caller (P19).

A project carries a margin. A site supervisor and the finance lead open the
**same project** and must see different fields of it — and the difference cannot
be a second query, because then two callers get two objects and somebody
eventually joins them.

**Stored as a reference, resolved on read.** The row holds `cost_line_id`, not a
number; resolving it consults the caller's scope. A denormalised margin on the
project row is a margin that leaks the first time anything selects `*` — and
something always eventually selects `*`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.domain.scopes import Department, Scope
from app.domain.session import ScopedSession


@dataclass(frozen=True, slots=True)
class FieldRule:
    """One field, and what it takes to see it."""

    name: str
    needs_scope: Scope
    needs_department: Department | None = None


# Doc 06's shape for the Operations first-party layer. Cost and margin are the
# fields that make this necessary: a subcontractor sees the milestone dates and
# must not see what the job earns.
PROJECT_FIELDS: Final[tuple[FieldRule, ...]] = (
    FieldRule("name", Scope.L2_COMPANY_INTERNAL),
    FieldRule("milestones", Scope.L2_COMPANY_INTERNAL),
    FieldRule("progress", Scope.L2_COMPANY_INTERNAL),
    FieldRule("cost_lines", Scope.L3_DEPARTMENT, Department.FINANCE),
    FieldRule("margin", Scope.L4_RESTRICTED, Department.FINANCE),
)


def visible_fields(
    caller: ScopedSession, rules: tuple[FieldRule, ...] = PROJECT_FIELDS
) -> frozenset[str]:
    """Which fields this caller may read.

    Returns names rather than filtering a dict, so the **query** can be built
    from it. Filtering after the fetch means the hidden value was already loaded
    into a process that then serialises objects for a living, and the only thing
    standing between it and the response is a `del`.
    """
    return frozenset(
        rule.name
        for rule in rules
        if caller.may_reach_scope(rule.needs_scope)
        and (rule.needs_department is None or rule.needs_department in caller.departments)
    )


def redact(row: dict[str, object], caller: ScopedSession) -> dict[str, object]:
    """Keep only what the caller may see. **Omits, never nulls.**

    A `margin: null` beside a populated project tells the reader a margin exists
    and is being withheld — which is a disclosure about the company's structure,
    and an invitation to go looking for it elsewhere.
    """
    allowed = visible_fields(caller)
    return {key: value for key, value in row.items() if key in allowed}
