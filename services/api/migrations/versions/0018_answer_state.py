"""A department answer is bound, or proposed.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-03

Q31/D22. A Contributor's answer to a department question is **proposed**, not
recorded — a department fact binds everyone in that department, and somebody
whose own scope is restricted to their own records cannot be the one who decides
what is true for all of them.

`doc/12` §Phase 7 calls this "migration 0015". That number went to P5's
domain-ownership lookup; this is 0018.

**Defaults to `bound`**, which is correct for every existing row: they were all
written by an Owner through a path that had no other state. A default of
`proposed` would retroactively un-fact everything the product already knows.

**NOT NULL and constrained to two values.** A third state would need a third
answer to "is this a fact?", and every reader would have to decide what to do
with it — which is how `ck_chunk_review_state` came to permit a vocabulary no
code could produce (migration 0010's story). A *rejected* proposal is deleted
with its reason in the audit trail rather than parked here, so nothing has to
filter it out for ever.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "onboarding_answer",
        sa.Column("answer_state", sa.Text(), nullable=False, server_default="bound"),
    )
    op.create_check_constraint(
        "ck_onboarding_answer_state",
        "onboarding_answer",
        "answer_state IN ('bound','proposed')",
    )
    # The review gate's only query until P13 builds it: what is waiting, and for
    # which department. Partial, because proposals are the rare row and a full
    # index would be mostly facts nobody is querying for this way.
    op.create_index(
        "ix_onboarding_answer_proposed",
        "onboarding_answer",
        ["workspace_id", "department"],
        postgresql_where=sa.text("answer_state = 'proposed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_onboarding_answer_proposed", table_name="onboarding_answer")
    op.drop_constraint("ck_onboarding_answer_state", "onboarding_answer", type_="check")
    op.drop_column("onboarding_answer", "answer_state")
