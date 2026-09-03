"""Resumable onboarding, and the departments that drive the product.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-03

`doc/12` §Phase 6 calls this "migration 0014". That number went to P5's company
registration, and 0015 to the domain-ownership lookup, so this is 0016. Said out
loud because a brief naming a revision is a brief someone will grep for.

**`onboarding_progress`** (Q28). Onboarding asks a founder for things they have
to go and find — a fiscal year start, goals nobody has written down. A flow that
demands all of it in one sitting gets abandoned in the middle, so the abandoned
state has to be worth returning to. One row per workspace: where they are, and
what is already done.

`completed` is a text array rather than a column per stage. Stages are a product
decision that will change — P7 adds department blocks, P8 adds documents — and a
schema that needs a migration every time the flow gains a step is a schema that
discourages improving the flow.

**`workspace_department`** (Q22, Q63). The selected set, and it is not a
preference: it decides which dashboards exist at all. Chief of Staff is never
stored here because it is automatic (Q24) — it consumes the others, so a company
that selected none would leave it reading nothing. Deriving it rather than
storing it means it cannot be deselected by a bad write.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPED = ("onboarding_progress", "workspace_department")


def upgrade() -> None:
    op.create_table(
        "onboarding_progress",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("current_stage", sa.Text(), nullable=False, server_default="company"),
        sa.Column(
            "completed",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "workspace_department",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("department", sa.Text(), primary_key=True),
        sa.Column(
            "selected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # `executive` is the Chief of Staff and is derived, never selected. Storing
    # it would make it deselectable by a bad write, and it is the one director
    # that must always exist.
    op.create_check_constraint(
        "ck_workspace_department_not_executive",
        "workspace_department",
        "department <> 'executive'",
    )

    for table in SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_workspace_isolation ON {table}
            USING (
                workspace_id
                = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
            )
            WITH CHECK (
                workspace_id
                = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
            )
            """
        )


def downgrade() -> None:
    for table in SCOPED:
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
    op.drop_table("workspace_department")
    op.drop_table("onboarding_progress")
