"""One person, one company.

`doc/11` §3.2 reversed the M:N assumption. A NEXUS account belongs to exactly
one company: a user with a live membership cannot create a second workspace, and
cannot accept an invitation into another one.

**The `membership` table stays many-to-many.** The rule is enforced here rather
than by a unique index, for two reasons:

- doc 06 §2.1's agency case — one operator, several client workspaces — is
  explicitly deferred rather than deleted, and a unique index would have to be
  migrated away again to bring it back.
- The rule is about *live* memberships. Someone who left a company must be able
  to join another, and a `UNIQUE (user_id)` cannot express "unless revoked"
  without becoming a partial index that then has to agree with application code
  anyway.

It lives in `app/domain/` and not in the two callers because a rule enforced at
each call site is a convention: the third caller forgets. Here there is one
place to attack and one place to audit — the same argument
`create_workspace_for_claim` makes for itself.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UserAlreadyInAWorkspaceError(Exception):
    """Raised when a second company would be joined or created.

    The message is shown to the person it happened to, so it says what to do.
    "Conflict" tells someone with one account and one company nothing at all.
    """

    def __init__(
        self,
        message: str = (
            "This account is already part of a company on NEXUS OS. "
            "A NEXUS account belongs to one company — ask an administrator "
            "there to change your role, or use a different email address to "
            "set up a separate company."
        ),
    ) -> None:
        super().__init__(message)


async def live_membership_count(
    db: AsyncSession, *, user_id: UUID, other_than: UUID | None = None
) -> int:
    """How many workspaces this user currently belongs to.

    `other_than` excludes one workspace from the count. That is what makes
    re-accepting an invitation to the workspace you are *already* in idempotent
    rather than a refusal — see `assert_no_live_membership`.

    Reads through the `membership_own_rows` policy from migration 0003, so
    `nexus.user_id` is set first — the same contract `memberships_for_user`
    documents. Without it the policy matches nothing and this would answer `0`
    for everybody, which fails **open**: every caller would be waved through.

    `revoked_at IS NULL` is the whole meaning of "live". See the class docstring.
    """
    await db.execute(text("SELECT set_config('nexus.user_id', :uid, true)"), {"uid": str(user_id)})
    count = (
        await db.execute(
            text(
                "SELECT count(*) FROM membership"
                " WHERE user_id = :uid AND revoked_at IS NULL"
                "   AND (:skip = '' OR workspace_id <> CAST(:skip AS uuid))"
            ),
            {"uid": str(user_id), "skip": str(other_than) if other_than else ""},
        )
    ).scalar_one()
    return int(count)


async def assert_no_live_membership(
    db: AsyncSession, *, user_id: UUID, other_than: UUID | None = None
) -> None:
    """Refuse if this user already belongs to a *different* company.

    Called by `create_workspace_for_claim` and by `invitations.accept` — the two
    paths that write a `membership` row.

    **`other_than` is the difference between a rule and a trap.** Accepting an
    invitation is idempotent by design: the insert is
    `ON CONFLICT DO NOTHING`, so re-clicking a link keeps the role you already
    hold rather than resetting it. Counting the user's own workspace would turn
    every second click into "you are already part of a company" — technically
    true, useless, and refusing the one case that was explicitly built to be
    safe. `test_an_existing_member_keeps_the_role_they_already_hold` caught
    exactly that when the first version of this guard omitted the parameter.
    """
    if await live_membership_count(db, user_id=user_id, other_than=other_than) > 0:
        raise UserAlreadyInAWorkspaceError
