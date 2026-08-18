"""Let a user see the workspace rows they hold a membership in.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-18

Migration 0003 solved exactly this problem one table too early. It let a user
see their own `membership` rows across workspaces, so the application could
answer "which workspaces do you belong to?" — but `memberships_for_user` joins
those rows to `workspace` to read the name and tenant, and `workspace` is
governed by the isolation policy from 0002, which needs `nexus.workspace_id`.

That GUC is not set during login: resolving *which* workspace is the outcome of
that query, not an input to it. So the join produced nothing, `memberships_for_user`
returned an empty list for a genuine member, and `current_scope` answered
403 "No workspace membership" to everyone. Every workspace-scoped route in the
product was unreachable, and no test caught it because the DB suites insert
workspaces themselves with the GUC already set.

The fix is the same shape as 0003 and rests on the same argument: this discloses
nothing the caller does not already possess — you know which companies you work
for — and it cannot reach a workspace you are not a member of, because the
predicate is an EXISTS over your own membership rows.

Three details that are load-bearing:

- **SELECT only.** A user may see where they belong; they may not write to it.
  The isolation policy still governs every INSERT and UPDATE, so a write still
  requires the workspace GUC set server-side.
- **`revoked_at IS NULL`.** A revoked membership must stop granting visibility
  immediately (doc 06 §4.15 — role change is immediate).
- **The subquery is itself under RLS.** `membership` has FORCE ROW LEVEL
  SECURITY, and the policy from 0003 exposes only rows whose `user_id` matches
  `nexus.user_id`. Adding the predicate here as well is belt and braces rather
  than the sole control.

PostgreSQL ORs permissive policies together, so this widens visibility by
precisely one row-set: the workspaces the caller is currently a member of.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY workspace_own_memberships ON workspace
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM membership m
                 WHERE m.workspace_id = workspace.id
                   AND m.user_id = NULLIF(current_setting('nexus.user_id', true), '')::uuid
                   AND m.revoked_at IS NULL
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workspace_own_memberships ON workspace")
