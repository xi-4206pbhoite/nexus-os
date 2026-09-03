"""The company brain.

Phase 13's central table, built from `doc/archive/neon-schema-before-the-d23-reset.md`
— a prior attempt recorded there precisely so this would not be designed twice.
Kept from it: versioning, the current version enforced by a **partial unique
index** rather than a flag, and an honest unavailable state in the schema.

**One change, and it is the point of the table.** That design had
`generated_by IN ('model','unavailable')`, so a workspace with no language model
could only ever hold an *unavailable* brain. But by the end of onboarding the
founder has told us what they sell, who they sell it to, what they are trying to
do and how each department works — every word of it typed by them, with the
question it answers still attached.

Assembling that is not generation. It invents nothing, and every line can name
where it came from, which is exactly I1. So `generated_by` admits `'answers'`:
a real brain, grounded, available with no API key — and the model enriches it
later rather than being the only way to have one at all.

`provenance` is `NOT NULL` with no default for that reason: a brain that cannot
say where a claim came from is the thing this product exists not to be.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_brain",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("profile", sa.Text),
        sa.Column("products_services", sa.Text),
        sa.Column("target_customers", sa.Text),
        sa.Column("brand_voice", sa.Text),
        sa.Column("goals", sa.Text),
        sa.Column("competitors", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        # What we proceeded on when the founder did not know. Separate from
        # `provenance` because an assumption and a fact want different
        # treatment everywhere downstream — including being contradicted by a
        # document later, which is the whole reason they are recorded.
        sa.Column("assumptions", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("provenance", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("generated_by", sa.Text, nullable=False, server_default="answers"),
        sa.Column("unavailable_reason", sa.Text, nullable=False, server_default=""),
        sa.Column("model_id", sa.Text),
        sa.Column("documents_read", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "version", name="uq_company_brain_version"),
        sa.CheckConstraint(
            "generated_by IN ('answers','model','unavailable')",
            name="ck_company_brain_generated_by",
        ),
        # An unavailable brain must say why. "We could not build one" with no
        # reason is indistinguishable from a bug, and the founder is the person
        # who has to decide whether to care.
        sa.CheckConstraint(
            "generated_by <> 'unavailable' OR unavailable_reason <> ''",
            name="ck_company_brain_unavailable_has_reason",
        ),
        # A grounded brain must be able to point at something. This is the
        # constraint that makes "never invent" structural rather than a habit.
        sa.CheckConstraint(
            "generated_by = 'unavailable' OR cardinality(provenance) > 0",
            name="ck_company_brain_grounded_has_provenance",
        ),
    )

    # One current brain per workspace, enforced by the database rather than by
    # an `is_current` flag two writers can both set.
    op.execute(
        "CREATE UNIQUE INDEX ux_company_brain_current"
        " ON company_brain (workspace_id) WHERE superseded_at IS NULL"
    )

    op.execute("ALTER TABLE company_brain ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company_brain FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_brain_workspace_isolation ON company_brain
            USING      (workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_brain_workspace_isolation ON company_brain")
    op.drop_table("company_brain")
