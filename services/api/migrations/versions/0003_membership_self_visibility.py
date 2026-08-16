"""Let a user see their own membership rows across workspaces.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16

The workspace-isolation policy from 0002 is correct and stays. But it creates a
bootstrapping problem for the agency case in doc 06 §2.1: to offer a workspace
switcher, the application must read *which* workspaces the caller belongs to —
and that is inherently a cross-workspace read, which the isolation policy
denies.

Resolving this by widening the isolation policy, or by reading memberships as a
privileged role, would both punch a hole straight through I3. Instead this adds
a second, deliberately narrow policy:

    a user may always see their own membership rows

It discloses nothing the caller does not already possess — you know which
companies you work for — and it cannot reach another person's membership,
because the predicate is `user_id = <the caller>`. The caller identity comes
from a GUC set server-side from the session, exactly like `nexus.workspace_id`,
so it is not a value the client can choose.

PostgreSQL ORs multiple permissive policies together, so this widens visibility
by precisely one row-set and nothing more.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY membership_own_rows ON membership
        FOR SELECT
        USING (
            user_id = NULLIF(current_setting('nexus.user_id', true), '')::uuid
        )
        """
    )
    # SELECT only. A user may see where they belong; they may not grant
    # themselves a role or change one — doc 06 §2.2 requires the inviter to set
    # it, and self-declaration is privilege escalation via dropdown.


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS membership_own_rows ON membership")
