"""When a workspace finished setup.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-18

Registration now ends somewhere — the flow collects details, department questions,
tool availability and a persona, and then says it is done. Nothing recorded that,
so "done" existed only as a client-side notion and any reload started the wizard
again.

**On `workspace`, not on `persona`**, and the distinction is not cosmetic. What
completes here is the *company* setup: which departments the company runs, its
currency, its fiscal year, what it sells. A second person accepting an invitation
does not redo any of that, and marking it per user would ask them to. Their own
persona is separate and already has its own row.

A timestamp rather than a boolean, so "when" is answerable — the morning brief needs
to know how long a workspace has been running before it can report a delta rather
than a baseline (doc 04 §6 rule 3), and `NULL` is the honest state for "never".

Deliberately **not** a precondition for anything yet. It records a fact; it does not
gate the dashboards, because the dashboards already degrade honestly on their own
inputs and adding a second gate would let a workspace be simultaneously set up and
locked out.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace",
        sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace", "setup_completed_at")
