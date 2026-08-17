"""Documents, chunks, and the vector index.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-17

**This is where pgvector stops being optional.** ADR 0004 deferred the hard
requirement to M5 precisely so that this migration could assert it, and
`/health/ready` has reported the extension's state on every call since M0 so its
absence could never be a surprise here.

The design decision that matters: **every scope field lives on the chunk row**,
alongside the embedding. Doc 03's schema carried only tenant, document and page,
which doc 06 §12 flags as unable to satisfy the pre-filter. With the fields on
the row, the permission predicate is an ordinary `WHERE` clause evaluated as part
of the ANN query rather than a pass over the results (I3). Post-filtering leaks
through ranking, result counts and latency, so this is not an optimisation.

`review_state` and `confidence` are columns, not derived values, because I4's
default-deny has to be visible in the data: a chunk that failed parsing or
classified below threshold sits at L5 with `review_state = 'pending_review'`, and
that must be queryable rather than recomputed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ADR 0003 — multilingual-e5-large. Deliberately the same width as voyage-3, so
# moving to a paid provider is a re-embed rather than a schema change.
EMBEDDING_DIM = 1024

WORKSPACE_SCOPED = ("document", "chunk")


def upgrade() -> None:
    # ── The hard requirement ──────────────────────────────────
    # Fatal from here. Everything below stores or indexes vectors, and a
    # database without the extension cannot serve this schema at all.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                RAISE EXCEPTION
                    'pgvector is required from this migration onward. It is not '
                    'installed on this database. Run db/bootstrap.sql as a '
                    'superuser first; on a managed provider the extension may '
                    'also need enabling in the console or parameter group.';
            END IF;
        END $$;
        """
    )

    # ── Documents ─────────────────────────────────────────────
    op.create_table(
        "document",
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
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        # Key in the object store, not the bytes.
        sa.Column("storage_key", sa.Text(), nullable=False),
        # Content hash, so a re-upload of identical bytes is recognisable.
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        # Doc 06 §5 requires the right-to-use warranty at upload. Recorded as a
        # fact with a timestamp, because "the customer warrants their right to
        # this content" is the practical control against someone indexing a
        # competitor's leaked price list.
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_text_version", sa.Text(), nullable=True),
        # Visible failure, never silent (doc 07 M5).
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        # Doc 06 §6 — a superseded document re-runs classification rather than
        # inheriting the old scope.
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_document_workspace", "document", ["workspace_id"])
    op.create_index("ix_document_status", "document", ["workspace_id", "status"])
    op.create_check_constraint(
        "ck_document_status",
        "document",
        "status IN ('pending','parsing','parsed','indexed','failed','quarantined')",
    )
    # Consent is a precondition for indexing, not a nicety.
    op.create_check_constraint(
        "ck_document_consent_before_indexing",
        "document",
        "status NOT IN ('indexed') OR consent_given_at IS NOT NULL",
    )

    # ── Chunks ────────────────────────────────────────────────
    op.create_table(
        "chunk",
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
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Citations depend on these two. A chunk never spans pages, so one
        # citation is always accurate for all of its content.
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_label", sa.Text(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        # ── Scope, on the row, so the predicate joins the ANN query (I3) ──
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column(
            "department",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        # L5 ownership. Non-null exactly when scope is L5.
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sensitivity", sa.Text(), nullable=False, server_default="normal"),
        # ── I4 default-deny, as queryable data ───────────────────
        sa.Column("classified_by", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_state", sa.Text(), nullable=False),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # Aggregates over a department are denied to a restricted Contributor
        # (ADR 0005); flagging the chunk lets that be part of the query.
        sa.Column(
            "is_dept_aggregate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # ── Embedding (ADR 0003) ─────────────────────────────────
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        # Stored per row so a future model change can identify what needs
        # re-embedding without guessing, and two models can coexist during a
        # transition.
        sa.Column("embedding_model_id", sa.Text(), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunk_document_ordinal"),
    )

    # Replace the placeholder array column with a real vector column. Done as
    # raw DDL because alembic has no native type for it.
    op.execute(f"ALTER TABLE chunk DROP COLUMN embedding")
    op.execute(f"ALTER TABLE chunk ADD COLUMN embedding vector({EMBEDDING_DIM})")

    op.create_check_constraint(
        "ck_chunk_scope", "chunk", "scope IN ('L1','L2','L3','L4','L5')"
    )
    op.create_check_constraint(
        "ck_chunk_sensitivity",
        "chunk",
        "sensitivity IN ('normal','financial','personal','restricted')",
    )
    op.create_check_constraint(
        "ck_chunk_review_state",
        "chunk",
        "review_state IN ('auto_approved','pending_review','approved','rejected')",
    )
    op.create_check_constraint("ck_chunk_confidence", "chunk", "confidence >= 0 AND confidence <= 1")
    # An L5 chunk with no owner would be visible to nobody — or, worse, to
    # everyone if a predicate treated NULL as a wildcard. I4 default-deny made
    # explicit in the schema.
    op.create_check_constraint(
        "ck_chunk_l5_has_owner", "chunk", "scope <> 'L5' OR owner_user_id IS NOT NULL"
    )
    # Same reasoning for L3: a department fact with no department cannot be
    # filtered by department.
    op.create_check_constraint(
        "ck_chunk_l3_has_department",
        "chunk",
        "scope <> 'L3' OR array_length(department, 1) >= 1",
    )
    # An embedded chunk must record which model produced it.
    op.create_check_constraint(
        "ck_chunk_embedding_provenance",
        "chunk",
        "embedding IS NULL OR (embedding_model_id IS NOT NULL AND embedding_dim IS NOT NULL)",
    )

    op.create_index("ix_chunk_document", "chunk", ["document_id"])
    # Supports the review queue without a scan.
    op.create_index(
        "ix_chunk_pending_review",
        "chunk",
        ["workspace_id", "review_state"],
        postgresql_where=sa.text("review_state = 'pending_review'"),
    )
    # The scope columns are indexed together because they are always queried
    # together — the predicate is never partial.
    op.create_index("ix_chunk_scope", "chunk", ["workspace_id", "scope"])
    op.execute("CREATE INDEX ix_chunk_department ON chunk USING gin (department)")

    # ── The ANN index ─────────────────────────────────────────
    # HNSW rather than IVFFlat: it does not need training data, and it degrades
    # far more gracefully under the selective pre-filters this schema applies.
    # Recall under those filters is measured by the M5 spike, not assumed.
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # ── Row-level security ────────────────────────────────────
    for table in WORKSPACE_SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE, not just ENABLE: migrations run as the table owner, and an
        # owner bypasses ENABLEd policies.
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
    op.drop_table("chunk")
    op.drop_table("document")
