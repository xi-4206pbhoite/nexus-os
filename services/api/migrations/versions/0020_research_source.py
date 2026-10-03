"""Per-source research outcomes.

`doc/12` P11. `research_run` already exists (0014); this is the fan-out beneath
it, and the reason it is a table rather than a JSON column on the run:
**one source failing never fails the run** (Q56), so each outcome has to be
writable and readable independently. A blob would make "the crawl succeeded and
the connector expired" a read-modify-write race between two workers.

`error_reason` is `NOT NULL` with an empty default and a constraint tying it to
the failed state. A source that failed without saying why makes a founder retry
the same thing, and "failed" alone is the message they cannot act on.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_source",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("run_id", sa.Uuid, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_reason", sa.Text, nullable=False, server_default=""),
        sa.Column("result_json", sa.JSON),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_run.id"], ondelete="CASCADE"),
        # One row per kind per run. Two workers claiming the same source would
        # otherwise each write an outcome and the last one would win silently.
        sa.UniqueConstraint("run_id", "kind", name="uq_research_source_kind"),
        sa.CheckConstraint(
            "kind IN ('crawl','audit','competitors','keywords','documents','connector')",
            name="ck_research_source_kind",
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','succeeded','failed','skipped','js_rendered')",
            name="ck_research_source_state",
        ),
        # A failure must say why, and only a failure may. The second half stops
        # a stale reason surviving a retry that then succeeded — which would put
        # an error message beside a green result.
        sa.CheckConstraint(
            "(state = 'failed') = (error_reason <> '')",
            name="ck_research_source_failure_has_reason",
        ),
    )
    op.create_index("ix_research_source_run", "research_source", ["run_id"])

    op.execute("ALTER TABLE research_source ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE research_source FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY research_source_workspace_isolation ON research_source
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
    op.execute("DROP POLICY IF EXISTS research_source_workspace_isolation ON research_source")
    op.drop_table("research_source")
