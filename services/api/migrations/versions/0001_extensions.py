"""Required Postgres extensions.

Revision ID: 0001
Revises:
Create Date: 2026-08-16

Scoped to extensions only. The tenancy tables (`tenant`, `user`, `workspace`,
`membership`) belong to M1, where they are designed together with row-level
security and the role-to-scope mapping — creating them here would pre-empt that
design and produce a migration that M1 immediately rewrites.

What this migration exists to prove is narrower and more useful: that migrations
run against the target database, and that **pgvector is actually available on
it**. Doc 07 §3 requires pgvector specifically so the permission predicate is an
ordinary SQL `WHERE` clause evaluated as part of the ANN query (I3). A managed
Postgres without the extension would fail much later, in M5, after a great deal
of work had been built on the assumption.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Vector similarity search with filterable columns — the basis of I3.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # gen_random_uuid() for primary keys, and digest() for content-addressed
    # chunk hashing in M5.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Fail loudly and immediately if the target cannot actually provide vector
    # search, rather than surfacing it as a confusing error in M5.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                RAISE EXCEPTION
                    'pgvector is not available on this database. NEXUS requires it: '
                    'the permission predicate must be part of the ANN query, not a '
                    'post-filter (doc 06 4.4). Use a Postgres that supports pgvector.';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Deliberately not dropped. Other databases on the same cluster may depend
    # on them, and dropping an extension cascades to every dependent object.
    pass
