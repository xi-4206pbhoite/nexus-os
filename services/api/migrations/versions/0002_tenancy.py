"""Tenancy: tenants, users, workspaces, memberships, sessions, personas, audit log.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16

Row-level security notes, because two details here decide whether isolation is
real or theatre:

1. **FORCE ROW LEVEL SECURITY, not just ENABLE.** A table's owner bypasses its
   RLS policies by default. Migrations run as `nexus_app`, which therefore owns
   these tables — so `ENABLE` alone would leave every policy inert for the very
   role the application connects as. Every isolation test would pass while
   proving nothing. `FORCE` closes that.

2. **The workspace comes from a GUC, not from a column the client controls.**
   Policies compare against `current_setting('nexus.workspace_id')`, which the
   application sets per request from the server-side session (doc 06 §2.1).
   `current_setting(..., true)` returns NULL when unset, and comparing to NULL
   yields NULL — which PostgreSQL treats as "not visible". So a connection that
   forgets to set the GUC sees nothing rather than everything. Default-deny by
   construction.

   `NULLIF(..., '')` is load-bearing: a GUC *cleared* to the empty string is a
   different state from one never set, and `''::uuid` raises rather than
   returning NULL. Without the NULLIF, the obvious "clear the workspace"
   implementation turns every subsequent query into a 500 instead of a clean
   deny. Fail-closed either way, but only one of those is a correct answer.

`app_user` is deliberately global rather than tenant-scoped: doc 06 §2.1
requires one identity across many client workspaces for the agency case, and
models users and workspaces many-to-many from day one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKSPACE_SCOPED = ("workspace", "membership", "persona", "audit_log")


def upgrade() -> None:
    # ── Tenants ───────────────────────────────────────────────
    op.create_table(
        "tenant",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── Users (global identity) ───────────────────────────────
    op.create_table(
        "app_user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Case-insensitive uniqueness: Parul@x.com and parul@x.com are one account.
    op.create_index("ix_app_user_email_lower", "app_user", [sa.text("lower(email)")], unique=True)

    # ── Workspaces ────────────────────────────────────────────
    op.create_table(
        "workspace",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("domain_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # `workspace_id` mirrors `id` so one RLS policy shape works on every
    # workspace-scoped table, this one included.
    op.execute("ALTER TABLE workspace ALTER COLUMN workspace_id SET DEFAULT gen_random_uuid()")
    op.create_index("ix_workspace_tenant", "workspace", ["tenant_id"])
    # M3 enforces one workspace per verified domain; the constraint lives here
    # so a second claim cannot land while that flow is being built.
    op.create_index(
        "ix_workspace_domain_verified",
        "workspace",
        [sa.text("lower(domain)")],
        unique=True,
        postgresql_where=sa.text("domain_verified_at IS NOT NULL"),
    )

    # ── Memberships (user x workspace, many-to-many) ──────────
    op.create_table(
        "membership",
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
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "departments",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        # Doc 06 §2.2 — role is set by the inviter, never self-declared at
        # acceptance. Recording who set it makes that auditable.
        sa.Column(
            "invited_by_user_id",
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
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )
    op.create_index("ix_membership_user", "membership", ["user_id"])
    op.create_check_constraint(
        "ck_membership_role",
        "membership",
        "role IN ('owner','executive','department_manager','contributor','viewer','external')",
    )

    # ── Sessions ──────────────────────────────────────────────
    # The active workspace lives here, server-side. Doc 06 §2.1: it is resolved
    # per request and never taken from a client-supplied value.
    op.create_table(
        "user_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "active_workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Only a hash is stored: a leaked database must not yield usable
        # session tokens.
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
    )
    op.create_index("ix_user_session_user", "user_session", ["user_id"])

    # ── Persona (doc 06 §2.6) ─────────────────────────────────
    # Presentation preference only. No field here is ever an input to the
    # retrieval predicate — conflating preference with authorisation is how
    # access-control bugs get written.
    op.create_table(
        "persona",
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
        sa.Column("stated_purpose", sa.Text(), nullable=True),
        sa.Column(
            "priority_topics",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("default_landing_screen", sa.Text(), nullable=True),
        sa.Column("communication_style", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=False, server_default="en"),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="Asia/Muscat"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_persona_workspace_user"),
    )

    # ── Audit log (doc 06 §9) ─────────────────────────────────
    # Itself access-controlled: it records queries and document titles.
    op.create_table(
        "audit_log",
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
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "impersonated_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_audit_log_workspace_at", "audit_log", ["workspace_id", "at"])

    # ── Row-level security ────────────────────────────────────
    for table in WORKSPACE_SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # See the module docstring: ENABLE alone is inert for the table owner,
        # which is the role the application connects as.
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
    for table in WORKSPACE_SCOPED:
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_isolation ON {table}")
    op.drop_table("audit_log")
    op.drop_table("persona")
    op.drop_table("user_session")
    op.drop_table("membership")
    op.drop_table("workspace")
    op.drop_index("ix_app_user_email_lower", table_name="app_user")
    op.drop_table("app_user")
    op.drop_table("tenant")
