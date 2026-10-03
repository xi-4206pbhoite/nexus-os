"""Mark an onboarding answer as an assumption rather than a statement.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-03

Phase 6's "not sure yet" stores the question's stated assumption instead of a
null — but a stored assumption that is indistinguishable from a stated fact is
only half the design, and the wrong half. Downstream has to be able to ask *did
they tell us this, or did we assume it?* before the Brain asserts anything from
it, before a dashboard tile presents it, and before the review gate decides
whether evidence contradicts it.

Defaults to `false`, which is correct for every row written before this: they
were all real answers. The column being NOT NULL is the point — a NULL here
would reintroduce exactly the third state the whole approach exists to remove.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "onboarding_answer",
        sa.Column(
            "is_assumption",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("onboarding_answer", "is_assumption")
