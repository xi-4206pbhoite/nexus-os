"""Which departments a company runs, and therefore which directors exist.

Q22, Q63. This is not a preferences screen. The selected set decides which
dashboards exist at all — a company that does not run a sales function should
not be shown a Sales Director with nothing in it, because an empty dashboard
reads as broken data rather than as an absent department.

**Chief of Staff is automatic** (Q24) and is never stored. It consumes the other
directors, so a company that selected none would leave it reading nothing — it
is not a choice worth offering. Deriving it here rather than writing a row means
no bad write can deselect the one director that must always exist; migration
0016 has a CHECK refusing `executive` outright, so the rule holds in the
database as well as in this function.

**Three to five is a recommendation, not a rule** (Q23). A company that runs two
functions should say two. The recommendation lives in the UI copy; nothing here
enforces a count, because a product that refuses to describe a business
accurately has chosen its own tidiness over the customer's reality.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.scopes import Department

# Always present, never selected. See the module docstring.
AUTOMATIC = Department.EXECUTIVE

SELECTABLE: tuple[Department, ...] = tuple(d for d in Department if d is not AUTOMATIC)

# Q23's guidance, stated here so the UI and any later validation read the same
# numbers rather than each carrying their own copy.
RECOMMENDED_MIN = 3
RECOMMENDED_MAX = 5


async def select_departments(
    db: AsyncSession, *, workspace_id: UUID, departments: Iterable[Department]
) -> frozenset[Department]:
    """Replace the selection wholesale.

    **Replace, not merge.** Changing your mind has to be able to remove a
    department: a merge would leave a director on the dashboard that nobody
    chose and no screen through which to get rid of it. Delete-then-insert in
    one transaction, so a reader never sees an empty selection mid-write.

    `executive` is filtered rather than rejected. A client that sends it is not
    misbehaving — it is describing the set it can see — and refusing the whole
    request over a value we were going to add anyway would be pedantry.
    """
    chosen = {d for d in departments if d is not AUTOMATIC}

    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )
    await db.execute(
        text("DELETE FROM workspace_department WHERE workspace_id = :w"),
        {"w": str(workspace_id)},
    )
    for department in sorted(chosen, key=lambda d: d.value):
        await db.execute(
            text("INSERT INTO workspace_department (workspace_id, department) VALUES (:w, :d)"),
            {"w": str(workspace_id), "d": department.value},
        )

    return frozenset(chosen | {AUTOMATIC})


async def selected_departments(db: AsyncSession, *, workspace_id: UUID) -> frozenset[Department]:
    """The selection, always including the Chief of Staff.

    Callers get one answer to "which directors does this company have" rather
    than a stored set they must remember to add `executive` to. Every place that
    forgot would be a missing dashboard.
    """
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )
    rows = (
        (
            await db.execute(
                text("SELECT department FROM workspace_department WHERE workspace_id = :w"),
                {"w": str(workspace_id)},
            )
        )
        .scalars()
        .all()
    )

    return frozenset({Department(r) for r in rows} | {AUTOMATIC})
