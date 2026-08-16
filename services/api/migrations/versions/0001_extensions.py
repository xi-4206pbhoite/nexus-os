"""Required Postgres extensions.

Revision ID: 0001
Revises:
Create Date: 2026-08-16

Scoped to extensions only. The tenancy tables (`tenant`, `user`, `workspace`,
`membership`) belong to M1, where they are designed together with row-level
security and the role-to-scope mapping — creating them here would pre-empt that
design and produce a migration that M1 immediately rewrites.

**On pgvector.** An earlier version of this migration hard-failed when pgvector
was absent. That was the right requirement in the wrong place: nothing before M5
performs vector search, so gating M0-M4 on it blocks work that does not need it.
See ADR 0004. The requirement has not been softened — it has moved:

- here:  `vector` is created **if available**, and its absence is recorded, not fatal
- M5:    a migration hard-requires it, because that is where indexing begins
- always: `/health/ready` reports pgvector as a distinct dependency state, so its
          absence is visible from day one rather than discovered in M5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() for primary keys, and digest() for content-addressed
    # chunk hashing in M5. Required now — a genuine hard dependency.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Vector similarity search with filterable columns — the basis of I3, where
    # the permission predicate is part of the ANN query rather than a
    # post-filter. Attempted here so a database that already has it is set up
    # correctly, but not required until M5.
    bind = op.get_bind()
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    ).first()

    if available is not None:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    else:
        # Deliberately a notice, not an exception. Visible in migration output
        # and in /health/ready; fatal only at M5.
        op.execute(
            """
            DO $$
            BEGIN
                RAISE NOTICE
                    'pgvector is not available on this server. Not required until M5, '
                    'but retrieval (M6) depends on it. /health/ready reports this.';
            END $$;
            """
        )


def downgrade() -> None:
    # Deliberately not dropped. Other databases on the same cluster may depend
    # on them, and dropping an extension cascades to every dependent object.
    pass
