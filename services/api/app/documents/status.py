"""A document's lifecycle status.

The value written to `document.status`, and the single source of truth for what
`ck_document_status` may permit. `tests/test_constraint_enum_parity.py` asserts
the two are set-equal in both directions.

This module exists because the constraint had **no** Python counterpart. Every
status was a bare string literal at the call site, so `'superseded'` was written
in one place and permitted in none, and the supersede path raised
`CheckViolation` on every use. There was nowhere for the mistake to be visible.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    """Every state a document row may hold.

    Five, not seven. The constraint originally also permitted `'parsing'` and
    `'parsed'`, which nothing has ever written: parsing happens synchronously
    inside the upload request, so a document is `pending` (the column default)
    until it is `indexed`, `failed` or `quarantined`. Migration 0010 removes
    them rather than adding them to this enum — a constraint wider than the code
    is vocabulary a later reader will take for a supported state. They return
    the day parsing moves to a worker, which is one line in each place.
    """

    PENDING = "pending"
    """The column default. A row that has been created but not yet resolved."""

    INDEXED = "indexed"
    """Parsed, chunked, classified and written. `ck_document_consent_before_indexing`
    makes recorded consent a precondition of reaching this state."""

    SUPERSEDED = "superseded"
    """Replaced by a later upload. The row survives for provenance; its chunks
    stop being reachable. Doc 06 §6 — a superseded document does not hand its
    scope to its replacement, which is re-classified from scratch."""

    FAILED = "failed"
    """Could not be read. The bytes are still stored: a file we failed to parse
    is still the customer's file, and discarding it would lose something they
    believe they gave us."""

    QUARANTINED = "quarantined"
    """An unsupported type. Distinct from `failed` so the count of scanned PDFs
    arriving without OCR is measurable rather than buried in parse errors."""
