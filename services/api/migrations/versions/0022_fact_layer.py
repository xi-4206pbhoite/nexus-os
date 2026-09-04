"""The fact layer: `brain_version` and `fact`.

`doc/12` P12. Facts live in versioned sets so "what did we believe in March" is
answerable — a brain that only holds current values cannot explain a number that
has since changed, and that explanation is most of what makes a number
trustworthy.

**`superseded_by` is a link, not a delete.** A fact never overwrites a fact:
the previous value stays with what replaced it, because "your revenue figure
changed" is a question somebody asks and a row updated in place cannot answer it.

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

TABLES = ("brain_version", "fact")


def upgrade() -> None:
    op.create_table(
        "brain_version",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.Uuid),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "version", name="uq_brain_version"),
    )

    op.create_table(
        "fact",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("brain_version_id", sa.Uuid, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("unit", sa.Text),
        # Where it came from, and precise enough to open. A fact whose source
        # cannot be opened is a fact nobody can check, which is the thing this
        # product exists not to produce.
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.Column("source_kind", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("precedence", sa.Integer, nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_by_id", sa.Uuid),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brain_version_id"], ["brain_version.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["fact.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "source_kind IN ('user_confirmed','connected_system','crawl','inference','document')",
            name="ck_fact_source_kind",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fact_confidence"),
        # Confirmation is a pair: who and when, or neither. Half a record of a
        # human decision is worse than none — it looks like an audit trail and
        # cannot answer the question one is kept for.
        sa.CheckConstraint(
            "(confirmed_by_user_id IS NULL) = (confirmed_at IS NULL)",
            name="ck_fact_confirmation_is_whole",
        ),
    )
    op.create_index("ix_fact_key", "fact", ["workspace_id", "key"])
    # The live set: one row per key per version, superseded rows excluded.
    op.execute(
        "CREATE UNIQUE INDEX ux_fact_current ON fact (brain_version_id, key)"
        " WHERE superseded_by_id IS NULL"
    )

    for table in TABLES:
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
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
        op.drop_table(table)
