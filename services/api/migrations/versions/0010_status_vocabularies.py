"""Reconcile the status vocabularies with the code that writes them.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-03

Two check constraints that no code path could satisfy. Both were certain runtime
failures on every use, and neither was caught because CI had no database and the
one test covering the upload path substituted the write (Phase 0 fixed that; this
is Phase 1 fixing what it exposed).

**`ck_chunk_review_state`.** The column permitted
`auto_approved · pending_review · approved · rejected`; `ReviewState` in
`app/documents/classify.py` produced
`auto_approved · needs_review · human_approved · quarantined`. One of four
values overlapped. Since `_classify_all` always withholds — there is no
classifier yet, which is I4 working as intended — every chunk of every upload
was written as `needs_review` and the whole transaction rolled back.

The SQL vocabulary is canonical rather than the Python one, because three things
already depended on it: the partial index `ix_chunk_pending_review`, the
review-queue listing, and its count query. All three selected `pending_review`,
a value nothing could write, so the queue was structurally empty even if an
insert had somehow succeeded. **This migration therefore changes no SQL** for
review state; the enum moved. The constraint is left exactly as 0007 wrote it,
and the fix is `app/documents/classify.py` plus
`tests/test_constraint_enum_parity.py`, which asserts the two lists are
set-equal in both directions from now on.

**`ck_document_status`.** This one is changed here. `'superseded'` was written
by the supersede path and permitted by nothing, so any upload carrying
`supersedes_id` raised — which is task 5.10's whole guarantee.

`'parsing'` and `'parsed'` go at the same time. Nothing has ever written them:
parsing happens synchronously inside the upload request, so a document is
`pending` until it is `indexed`, `failed` or `quarantined`. A constraint wider
than the code is vocabulary a later reader will take for a supported state, and
the parity test now forbids it. They return the day parsing moves to a worker.

The rewrite is safe on any existing data: `document` holds no row in either
state, and the migration verifies that rather than assuming it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept as literals rather than imported from `app.documents.status`. A migration
# describes the schema at a point in time; importing the enum would make this
# file's meaning change whenever the enum does, and a later edit there would
# silently rewrite history. `tests/test_constraint_enum_parity.py` is what binds
# the two together, against the database, on every run.
STATUSES = ("pending", "indexed", "superseded", "failed", "quarantined")
RETIRED = ("parsing", "parsed")


def upgrade() -> None:
    # Verify before rewriting. Narrowing a constraint under rows that violate it
    # fails anyway, but with a message about the constraint rather than about
    # the data — and this states the assumption the docstring makes.
    bind = op.get_bind()
    stranded = bind.execute(
        sa.text("SELECT count(*) FROM document WHERE status = ANY(:retired)"),
        {"retired": list(RETIRED)},
    ).scalar_one()
    if stranded:
        raise RuntimeError(
            f"{stranded} document row(s) hold a status this migration retires "
            f"({', '.join(RETIRED)}). Nothing in the application writes these, so "
            "resolve them by hand before continuing rather than losing the state."
        )

    op.drop_constraint("ck_document_status", "document", type_="check")
    op.create_check_constraint(
        "ck_document_status",
        "document",
        "status IN ('pending','indexed','superseded','failed','quarantined')",
    )


def downgrade() -> None:
    # Back to 0007's vocabulary. A superseded document cannot be represented
    # there, so it becomes `indexed` again — which is what it was before being
    # replaced, and is the only value that keeps the consent constraint
    # satisfied. Recorded here because it is a lossy step, not a symmetric one.
    op.execute("UPDATE document SET status = 'indexed' WHERE status = 'superseded'")
    op.drop_constraint("ck_document_status", "document", type_="check")
    op.create_check_constraint(
        "ck_document_status",
        "document",
        "status IN ('pending','parsing','parsed','indexed','failed','quarantined')",
    )
