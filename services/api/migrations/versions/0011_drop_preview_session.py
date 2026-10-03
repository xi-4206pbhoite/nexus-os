"""Drop `preview_session` — the pre-signup audit is retired.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-03

`doc/11` Q1 (D18) removed the unauthenticated Preview audit from the product.
This is the storage half of that removal.

**Dropping the table is the point, not a tidy-up.** `preview_session` held a
reduced audit of a domain whose owner had no account here, could not see what we
held, and could not ask anyone to delete it. Doc 06 §10 answered that with a TTL
and a deletion-request path, and `jobs/expiry.py` swept the rows on a schedule.
With no unauthenticated crawl there is no third-party data, so the obligation
does not need honouring — it does not arise. That is what makes **D9 void**
rather than deferred, and it is a better outcome than any sweep: the safest
retention policy is having nothing to retain.

**`rate_limit_counter` stays.** It was created alongside this table in 0004 and
reads as part of the same feature, but it is not: the limiter survives, re-keyed
from `(ip, domain, global)` to `(workspace, global)`, and guards authenticated
research runs in P11. Its rows are counters keyed by an opaque bucket string, so
the re-keying needs no migration — the old buckets simply age out through
`purge_expired`.

The downgrade recreates the table as 0004 built it. It does not restore any
rows; they are gone, deliberately, and a downgrade that silently produced an
empty table where the operator expected data would be worse than one that says
so here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The indexes and the check constraint go with the table; naming them
    # separately would only matter if either could outlive it.
    op.drop_table("preview_session")


def downgrade() -> None:
    op.create_table(
        "preview_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("requested_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("audit_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
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
    op.create_index("ix_preview_session_expires", "preview_session", ["expires_at"])
    op.create_check_constraint(
        "ck_preview_session_status",
        "preview_session",
        "status IN ('pending','running','complete','failed','blocked')",
    )
