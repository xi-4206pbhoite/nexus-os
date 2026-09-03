"""Where a founder is in onboarding, and what they have already finished.

Q28. The flow asks for things people have to go and look up — a fiscal year
start, three goals nobody has written down, a list of competitors. Any version
that demands all of it in one sitting will be abandoned partway, so the
half-finished state is the normal state and has to be worth returning to.

**Progress lives in the database, not the session.** A cookie or an in-memory
map would pass every test that keeps the session and fail the founder who closed
the tab, which is the only case that matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# The spine. P7 inserts department blocks and P8 documents; the order here is
# the order a founder walks, and `next_stage` reads it rather than hard-coding
# transitions, so adding a stage is one edit.
STAGES: tuple[str, ...] = ("company", "departments", "review")


@dataclass(frozen=True, slots=True)
class Progress:
    current: str
    completed: frozenset[str]

    @property
    def finished(self) -> bool:
        return set(STAGES) <= self.completed


def next_stage(after: str) -> str:
    """The stage following `after`, or the last one if there is none.

    Clamped rather than wrapping or raising: a founder who finishes the final
    stage should stay on it, and a stage name that is not in `STAGES` — a rename
    mid-flight, a stale client — should not take down the request that reports
    progress.
    """
    if after not in STAGES:
        return STAGES[0]
    index = STAGES.index(after)
    return STAGES[min(index + 1, len(STAGES) - 1)]


async def progress_for(db: AsyncSession, *, workspace_id: UUID) -> Progress:
    """Read progress, defaulting to the first stage.

    A workspace with no row has not started, which is the same thing as being on
    the first stage with nothing completed — so this returns that rather than
    `None`. Callers would otherwise each invent the same default, and one of
    them would invent it differently.
    """
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )
    row = (
        await db.execute(
            text(
                "SELECT current_stage, completed FROM onboarding_progress WHERE workspace_id = :w"
            ),
            {"w": str(workspace_id)},
        )
    ).first()

    if row is None:
        return Progress(current=STAGES[0], completed=frozenset())
    return Progress(current=row.current_stage, completed=frozenset(row.completed or ()))


async def complete_stage(db: AsyncSession, *, workspace_id: UUID, stage: str) -> Progress:
    """Mark a stage done and move on — **without ever moving backwards**.

    The obvious implementation sets `current_stage` to whatever follows the
    stage just completed. That reverses a founder who has since gone further: a
    double-clicked Continue, a replayed POST, a browser restoring a tab. It is
    the same defect shape as finding #9, where a second click on create-workspace
    permanently disputed the user's own claim.

    So the new stage is the **later** of where they are and where this completion
    would take them, computed in SQL so two concurrent requests cannot both read
    the old value and both write.
    """
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )

    current = (await progress_for(db, workspace_id=workspace_id)).current
    candidate = next_stage(stage)
    onward = candidate if STAGES.index(candidate) > STAGES.index(current) else current

    await db.execute(
        text(
            "INSERT INTO onboarding_progress (workspace_id, current_stage, completed)"
            " VALUES (:w, :stage, ARRAY[:done]::text[])"
            " ON CONFLICT (workspace_id) DO UPDATE SET"
            "   current_stage = :stage,"
            # `array_agg(DISTINCT ...)` rather than append: completing a stage
            # twice must not put it in the list twice, and a duplicate would
            # make `completed` a log rather than a set.
            "   completed = ("
            "     SELECT array_agg(DISTINCT s) FROM unnest("
            "       onboarding_progress.completed || ARRAY[:done]::text[]) AS s),"
            "   updated_at = now()"
        ),
        {"w": str(workspace_id), "stage": onward, "done": stage},
    )
    return await progress_for(db, workspace_id=workspace_id)
