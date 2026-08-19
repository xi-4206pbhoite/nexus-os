"""`superseded` is a document status the constraint never allowed.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-18

A second defect on the same write path as the `review_state` spelling, and found
the same way — by looking for what `tests/test_document_upload.py` could not see
with `_record` substituted.

`app/routes/documents.py` retires a replaced document with
`UPDATE document SET status = 'superseded'`, implementing doc 06 §6: a superseded
document does not hand its scope to its replacement, so its chunks stop being
reachable while the row survives for provenance. But migration 0007's
`ck_document_status` lists only
`('pending','parsing','parsed','indexed','failed','quarantined')`.

So every supersede raised `CheckViolation`, and because that UPDATE shares the
upload's transaction, it rolled back the *replacement* document too. Uploading a
new version of a price list would have failed outright and left the old one
authoritative — the worst available outcome for the module doc 01 §5 M8 calls the
highest-liability one in the product.

`superseded` is added rather than the UPDATE being changed, because the state is
real and doc 06 §6 requires it. It is deliberately *not* added to
`ck_document_consent_before_indexing`: that constraint names `indexed` only, and a
superseded document had already recorded consent when it was indexed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALLOWED = (
    "pending",
    "parsing",
    "parsed",
    "indexed",
    "superseded",
    "failed",
    "quarantined",
)


def _values(names: tuple[str, ...]) -> str:
    return ",".join(f"'{n}'" for n in names)


def upgrade() -> None:
    op.drop_constraint("ck_document_status", "document", type_="check")
    op.create_check_constraint(
        "ck_document_status",
        "document",
        f"status IN ({_values(_ALLOWED)})",
    )


def downgrade() -> None:
    # A row already at 'superseded' would fail the narrower constraint, so it is
    # returned to 'indexed' first — the state it held before being retired.
    # Recorded rather than silent: this loses the fact that it was superseded.
    op.execute("UPDATE document SET status = 'indexed' WHERE status = 'superseded'")
    op.drop_constraint("ck_document_status", "document", type_="check")
    op.create_check_constraint(
        "ck_document_status",
        "document",
        f"status IN ({_values(tuple(n for n in _ALLOWED if n != 'superseded'))})",
    )
