"""Preview sessions and rate-limit counters.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

Two tables serving the unauthenticated path, and neither is workspace-scoped —
by definition, since no workspace exists yet.

**`preview_session`** holds a reduced audit of a domain nobody has verified they
own. Doc 06 §1.1 and §10 require a short TTL and a deletion path for the crawled
company, *which has no account here*. That obligation is unusual enough to be
worth stating: the subject of this data is not our user.

**`rate_limit_counter`** lives in Postgres rather than Redis on purpose (ADR
0001 — fewer moving parts, and no Redis in the native stack). Fixed windows are
coarser than a sliding log but need one row per key per window, and the ceiling
here is about cost containment rather than precision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # The domain as entered, normalised. Not a foreign key to anything:
        # this company has no account and may never have one.
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("requested_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("audit_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        # Retained to enforce per-IP limits and to answer abuse reports. Not a
        # marketing signal, and it expires with the row.
        sa.Column("requester_ip_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by_workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_preview_session_domain", "preview_session", [sa.text("lower(domain)")])
    # Drives the expiry sweep.
    op.create_index("ix_preview_session_expires", "preview_session", ["expires_at"])
    op.create_check_constraint(
        "ck_preview_session_status",
        "preview_session",
        "status IN ('pending','running','complete','failed','blocked')",
    )

    op.create_table(
        "rate_limit_counter",
        # e.g. 'ip:sha256(...)', 'domain:example.com', 'global:preview'
        sa.Column("bucket", sa.Text(), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_rate_limit_window", "rate_limit_counter", ["window_start"])


def downgrade() -> None:
    op.drop_table("rate_limit_counter")
    op.drop_index("ix_preview_session_expires", table_name="preview_session")
    op.drop_index("ix_preview_session_domain", table_name="preview_session")
    op.drop_table("preview_session")
