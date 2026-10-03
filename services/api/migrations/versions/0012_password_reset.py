"""Password reset tokens.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-03

Deliberately shaped exactly like `email_verification` from migration 0005, and
for the same reasons: the token is **hashed at rest**, **single-use** and
**expiring**. A leaked database must not yield working reset links, and a
consumed link must not reset a password twice.

A separate table rather than a `purpose` column on `email_verification`. The two
tokens have different lifetimes and very different blast radii — a stolen
verification token confirms an address, a stolen reset token *is* the account —
and a shared table invites a query that forgets to filter on purpose, which
would let one be redeemed as the other.

`user_id` is not unique. Requesting a second reset supersedes the first in
application code (`app/auth/password_reset.py`) rather than by constraint,
because superseding must also work when the first is already expired, and a
unique index would have to be dropped to allow the history this leaves behind.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset",
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
        # SHA-256 of the token. The token itself exists only in the email.
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The lookup the confirm path makes, and the only one it makes.
    op.create_index("ix_password_reset_token", "password_reset", ["token_hash"])
    # Drives superseding an outstanding token when a second reset is requested.
    op.create_index("ix_password_reset_user", "password_reset", ["user_id"])


def downgrade() -> None:
    op.drop_table("password_reset")
