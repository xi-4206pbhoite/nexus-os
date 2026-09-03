"""What an unverified workspace may not do.

**D19 reversed a rule and this module is the half that survived.**

Doc 07 M3's acceptance was *"no workspace exists without a verified domain"*,
enforced by making `create_workspace_for_claim` the only path that could insert
one. It was a real guarantee and it had a real cost: verification is a DNS record
or a file upload, so a signed-up user faced a systems administration task before
they could see anything at all. Every `CurrentScope` endpoint answered 403 until
it was done.

The split asks a sharper question — *what was verification actually protecting?*
Not the existence of a workspace. Two things:

- **Inviting people.** An invitation adds somebody to a company, and the only
  evidence that this is *your* company is the domain. Without it, anyone could
  register `acme.om`, invite `finance@acme.om`, and receive whatever that person
  brought with them.
- **Connecting tools.** A connector pulls a company's own data in. Attaching one
  to a workspace nobody has proved they own is the same problem with the arrow
  reversed.

Both still require a proved domain. Everything else — onboarding, uploading your
own documents, looking around — does not, because the only person harmed by
getting those wrong is the person doing it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UnverifiedWorkspaceError(Exception):
    """Raised when an unverified workspace attempts a verification-gated act.

    The message is shown to the person it happened to and names the way out.
    "Forbidden" tells a founder who has just created their company nothing at
    all, and the thing they need to hear is that this is a step they can take
    themselves in Settings rather than something being wrong with their account.
    """

    def __init__(
        self,
        action: str = "that",
        message: str | None = None,
    ) -> None:
        super().__init__(
            message
            or (
                f"Verify your domain before {action}. It proves the company is "
                "yours, which is what stops somebody else registering it and "
                "inviting your colleagues. Settings has the DNS record to add, "
                "or a file to publish."
            )
        )
        self.action = action


async def is_domain_verified(db: AsyncSession, *, workspace_id: UUID) -> bool:
    """Read the flag through whatever scope the caller already has.

    Deliberately a plain read rather than something taking a `ScopedSession`:
    the callers are gates on their own routes, which have already resolved the
    caller's authority. What this answers is a fact about the workspace, not a
    question about who is asking.
    """
    verified = (
        await db.execute(
            text("SELECT domain_verified_at FROM workspace WHERE id = :w"),
            {"w": str(workspace_id)},
        )
    ).scalar()
    return verified is not None


async def require_verified_domain(
    db: AsyncSession, *, workspace_id: UUID, action: str = "that"
) -> None:
    """Refuse if the domain is not proved.

    Called by invitations and by connectors — the two acts D19 kept behind
    verification. A third caller should be argued for rather than added: the
    list being short is what makes the split defensible, and a gate that creeps
    back over everything is the old rule with extra steps.
    """
    if not await is_domain_verified(db, workspace_id=workspace_id):
        raise UnverifiedWorkspaceError(action)
