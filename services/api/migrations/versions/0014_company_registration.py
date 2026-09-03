"""Company registration: extra research URLs, join requests, research runs.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-03

`doc/12` §Phase 5 calls this "migration 0013". That number was taken by the
`domain_claim` RLS work, which D24 forced ahead of it — so this is 0014. Worth
saying rather than silently renumbering: a brief that names a revision is a brief
someone will grep for.

Three tables, and one of them changes a rule.

**`workspace_url`** — the additional URLs a company adds for research (`doc/11`
Q16). Deliberately separate from `workspace.domain`, which is the *one*
registered domain and the only one that can be verified. Collapsing them would
mean a company could add a URL and imply ownership of it, which is exactly what
domain verification exists to stop.

**`join_request`** — `doc/11` Q8. When someone registers a company whose domain
already belongs to a verified workspace, the honest answer is "that company is
already here" rather than a second workspace for the same business. Creating a
separate one stays possible and must be explicitly confirmed.

**`research_run`** — enqueue only. P11 builds the engine; this phase records that
a run was asked for, so the request survives a restart and the queue is visible
before there is anything to drain it.

All three are workspace-scoped and carry the same isolation policy as every other
workspace table, with one exception argued at its own definition below.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPED = ("workspace_url", "research_run")


def upgrade() -> None:
    # ── The five registration fields (`doc/12` §Phase 5) ──────
    #
    # `workspace` has carried `name` and `domain` since migration 0002 and
    # nothing else about the business. Registration asks for five things, and
    # four of them had nowhere to go.
    #
    # All nullable: every workspace created before this migration has none of
    # them, and backfilling a currency or a headcount band would mean inventing
    # facts about a real company — which is the one thing this product must
    # never do. A NULL here reads as "not asked yet", which is true.
    op.add_column("workspace", sa.Column("website_url", sa.Text(), nullable=True))
    op.add_column("workspace", sa.Column("country", sa.Text(), nullable=True))
    op.add_column("workspace", sa.Column("reporting_currency", sa.Text(), nullable=True))
    op.add_column("workspace", sa.Column("headcount_band", sa.Text(), nullable=True))

    op.create_table(
        "workspace_url",
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
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "added_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workspace_id", "url", name="uq_workspace_url"),
    )

    op.create_table(
        "research_run",
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
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_research_run_state",
        "research_run",
        "state IN ('queued','running','complete','failed')",
    )
    # The queue's only query until P11: what is waiting, oldest first.
    op.create_index(
        "ix_research_run_queued",
        "research_run",
        ["requested_at"],
        postgresql_where=sa.text("state = 'queued'"),
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

    # ── join_request, and why its policy is not the usual one ──
    #
    # A join request is written by somebody who is **not yet a member** of the
    # workspace it targets, and read by an Owner who **is**. The workspace
    # predicate cannot serve both: the requester has no membership, so with
    # `nexus.workspace_id` set to the target they would be claiming a scope they
    # do not hold, and with it unset they could not insert at all.
    #
    # So the policy is a union of the two legitimate readers, and each half is
    # narrow: you see a request if you wrote it, or if it targets the workspace
    # you are currently scoped to. The Owner-only restriction on *approving* is
    # an application concern (`require_executive_surface`), not this policy's —
    # the policy decides visibility, the route decides authority.
    op.create_table(
        "join_request",
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
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "decided_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_join_request_state",
        "join_request",
        "state IN ('pending','approved','declined','withdrawn')",
    )
    # One live request per person per workspace. Without this, a refresh or an
    # impatient click produces a queue of identical requests for an Owner to
    # wade through, and "already requested" stops being answerable.
    op.create_index(
        "uq_join_request_pending",
        "join_request",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
    )

    op.execute("ALTER TABLE join_request ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE join_request FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY join_request_requester_or_workspace ON join_request
        USING (
            user_id = NULLIF(current_setting('nexus.user_id', true), '')::uuid
            OR workspace_id
               = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
        )
        WITH CHECK (
            user_id = NULLIF(current_setting('nexus.user_id', true), '')::uuid
        )
        """
    )
    # Note the asymmetry: USING permits both readers, WITH CHECK permits only
    # the requester. An Owner may see and decide a request; they may not author
    # one on somebody else's behalf, which would be a membership granted by the
    # person granting it.


def downgrade() -> None:
    for column in ("headcount_band", "reporting_currency", "country", "website_url"):
        op.drop_column("workspace", column)
    op.execute("DROP POLICY IF EXISTS join_request_requester_or_workspace ON join_request")
    op.drop_table("join_request")
    for table in SCOPED:
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
    op.drop_table("research_run")
    op.drop_table("workspace_url")
