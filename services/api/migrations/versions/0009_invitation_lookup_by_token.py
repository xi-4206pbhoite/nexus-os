"""Let an invitation be found by the token that was sent with it.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-18

Acceptance has a bootstrapping problem of its own. `invitation` is
workspace-scoped and carries the isolation policy from migration 0006, which
compares against `nexus.workspace_id`. But the person accepting is not yet in
the workspace — that is what accepting *does* — so there is no scope to set the
GUC from, and the workspace is not knowable until the invitation row has been
read. The row cannot be read to learn the workspace, and the workspace must be
known to read the row.

The options were to widen the isolation policy, to read invitations as a
privileged role, or this: a second, deliberately narrow policy that exposes
**exactly the row whose token hash the caller already presented**.

    a row is visible to a connection that already knows its token hash

The application sets `nexus.invitation_token_hash` to the SHA-256 of the token
in the link, inside the same transaction. That discloses nothing the caller did
not already hold — the hash is derived from the token, and the token is the
credential — and it cannot enumerate: there is no `LIKE`, no range, and a hash
the caller cannot produce matches no row.

Three details:

- **SELECT only.** Marking the invitation accepted is an UPDATE, and it still
  goes through the isolation policy — by which point the workspace *is* known,
  because the row has just been read. So the write is scoped normally.
- **The GUC is transaction-local** (`set_config(..., true)`), like every other
  one in this system. A session-level setting would survive the connection's
  return to the pool and leave the next caller able to see that invitation.
- **No expiry or revocation predicate here.** Visibility is not authorisation:
  the application decides whether an invitation is still usable, and it needs to
  read `expires_at` and `revoked_at` to say *why* it is not. A policy that hid
  expired rows would collapse "expired" and "never existed" into one answer at
  the wrong layer.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY invitation_by_token_hash ON invitation
        FOR SELECT
        USING (
            token_hash = NULLIF(current_setting('nexus.invitation_token_hash', true), '')
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS invitation_by_token_hash ON invitation")
