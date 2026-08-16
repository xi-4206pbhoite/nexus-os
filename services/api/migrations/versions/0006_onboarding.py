"""Onboarding answers and invitations.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-17

`onboarding_answer` stores the **scope with the answer**, per doc 06 §2.5. The
columns are not decoration: a form is not a laundering mechanism, and an average
deal size typed at signup is an L3 Sales fact exactly as it would be if it
arrived from a CRM.

`invitation` records **who set the role**. Doc 06 §2.2: *"Every subsequent
user's role is set by the inviter, never self-declared at acceptance.
Self-declared role is privilege escalation via dropdown."* The role therefore
lives on the invitation, written by the inviter, and acceptance copies it —
acceptance never supplies it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "onboarding_answer",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "answered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question_key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        # Tagged at capture, not inferred later.
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workspace_id", "question_key", name="uq_onboarding_answer"),
    )
    op.create_check_constraint(
        "ck_onboarding_answer_scope",
        "onboarding_answer",
        "scope IN ('L1','L2','L3','L4','L5')",
    )
    # An L3 answer with no department cannot be filtered by department, which
    # would make it reachable by anyone with any L3 access.
    op.create_check_constraint(
        "ck_onboarding_answer_l3_has_department",
        "onboarding_answer",
        "scope <> 'L3' OR department IS NOT NULL",
    )

    op.create_table(
        "invitation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        # Set by the inviter. Acceptance copies it; acceptance never supplies it.
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "departments",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_invitation_workspace", "invitation", ["workspace_id"])
    op.create_check_constraint(
        "ck_invitation_role",
        "invitation",
        "role IN ('owner','executive','department_manager','contributor','viewer','external')",
    )

    for table in ("onboarding_answer", "invitation"):
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
    for table in ("onboarding_answer", "invitation"):
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
    op.drop_table("invitation")
    op.drop_table("onboarding_answer")
