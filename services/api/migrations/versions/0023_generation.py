"""`generation` — what was asked, what was computed, and what it cost.

`doc/12` P14. Every model call leaves a row, and the row is what makes "why are
you telling me this?" answerable months later.

**`input_snapshot` inherits its inputs' scope tag and retention**, and that is
the load-bearing part. A snapshot of L4 facts is itself L4: storing the
question's inputs in a table with weaker rules than the facts they came from
would be a side door around the whole scope lattice — read the restricted number
once, and it lives on unrestricted forever. `scope_key` carries the tag, RLS
carries the isolation, and the export/deletion paths must include this table for
the same reason.

**`calculation_trace` is separate from `input_snapshot`.** The inputs say what
we had; the trace says what we did with them. A dispute about a number is nearly
always about the second, and merging them into one blob makes the arithmetic
unreadable exactly when somebody needs to read it.

Revision ID: 0023
Revises: 0022
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("module", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=False),
        # What we had, and what we did with it. Separate on purpose.
        sa.Column("input_snapshot", sa.JSON, nullable=False),
        sa.Column("calculation_trace", sa.JSON, nullable=False),
        # The tag the snapshot inherits from its inputs. Without it this table
        # is a side door around the scope lattice.
        sa.Column("scope_key", sa.Text, nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("unavailable_reason", sa.Text, nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("requested_by_user_id", sa.Uuid),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.CheckConstraint("outcome IN ('answered','unavailable')", name="ck_generation_outcome"),
        # An unavailable generation must say which kind. "Unavailable" with no
        # reason is indistinguishable from a bug, and this table exists to be
        # read when somebody is already suspicious.
        sa.CheckConstraint(
            "(outcome = 'unavailable') = (unavailable_reason <> '')",
            name="ck_generation_reason_matches_outcome",
        ),
        # Cost is never negative. A refund or a correction is another row, not
        # an edit — the same reason `fact` supersedes rather than updates.
        sa.CheckConstraint("cost_micros >= 0", name="ck_generation_cost_non_negative"),
    )
    op.create_index("ix_generation_workspace_day", "generation", ["workspace_id", "created_at"])
    # The daily budget reads this. Without the index it scans every generation
    # the workspace has ever made, on every request that might make one.
    op.create_index("ix_generation_user_day", "generation", ["requested_by_user_id", "created_at"])

    op.execute("ALTER TABLE generation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE generation FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY generation_workspace_isolation ON generation
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
    op.execute("DROP POLICY IF EXISTS generation_workspace_isolation ON generation")
    op.drop_table("generation")
