"""Email verification and domain claims.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-16

Doc 06 §1.1: *"Anyone can type a competitor's URL. Without a check, NEXUS crawls
a company the registrant does not own, produces an audit of it, names its
competitors, and hands that to a stranger — a competitive-intelligence product
sold by accident."*

`domain_claim` is the record of *how* someone proved ownership, kept separately
from the outcome on `workspace.domain_verified_at`, for three reasons doc 06 §1.1
requires and one it implies:

- **Methods are not equivalent.** DNS TXT and a file at a known path prove
  control of the domain. A same-domain email address proves *employment*, not
  authority — so `strength` is a stored fact, not an inference, and a weak claim
  flags Owner-claim review when a second person from the same domain appears.
- **Verification is re-checked on a cadence**, so the challenge must survive
  the initial check. `next_check_at` drives that.
- **Revocation** when the verifying method stops resolving needs somewhere to
  record that it stopped.
- **Disputes** need a home. First verified wins, and the second claimant enters
  a dispute rather than silently failing or silently succeeding.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Email verification ────────────────────────────────────
    op.create_table(
        "email_verification",
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
        # Hashed, like a session token: a leaked database must not yield a
        # working verification link.
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Single use. A consumed token must not verify a second account.
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_email_verification_user", "email_verification", ["user_id"])

    # ── Domain claims ─────────────────────────────────────────
    op.create_table(
        "domain_claim",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("strength", sa.Text(), nullable=False),
        # The value the claimant must publish. Random per claim, so proving one
        # domain never helps prove another.
        sa.Column("challenge_token", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="pending"),
        # What was actually observed, for support and for the audit trail.
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        # Drives re-verification (doc 06 §1.1 requires a cadence).
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Set when this claim lost a race for the domain.
        sa.Column(
            "disputes_workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_domain_claim_domain", "domain_claim", [sa.text("lower(domain)")])
    op.create_index("ix_domain_claim_user", "domain_claim", ["user_id"])
    op.create_index("ix_domain_claim_next_check", "domain_claim", ["next_check_at"])
    op.create_check_constraint(
        "ck_domain_claim_method", "domain_claim", "method IN ('dns_txt','file','email','manual')"
    )
    op.create_check_constraint(
        "ck_domain_claim_strength", "domain_claim", "strength IN ('strong','weak')"
    )
    op.create_check_constraint(
        "ck_domain_claim_state",
        "domain_claim",
        "state IN ('pending','verified','failed','expired','revoked','disputed')",
    )
    # One live attempt per person per domain, so retrying does not accumulate
    # challenge tokens that all remain valid.
    op.create_index(
        "uq_domain_claim_pending",
        "domain_claim",
        [sa.text("lower(domain)"), "user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
    )

    # Doc 06 §1.1 — a weak (email) claim flags the workspace for Owner-claim
    # review if a second person from the same domain registers.
    op.add_column(
        "workspace",
        sa.Column(
            "owner_claim_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("workspace", sa.Column("verification_method", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace", "verification_method")
    op.drop_column("workspace", "owner_claim_review")
    op.drop_table("domain_claim")
    op.drop_table("email_verification")
