"""Task 5.6 — turning classified chunks into searchable ones.

This module decides one thing: **may this document call itself `indexed`?**

`indexed` is a promise that the content is retrievable. Nothing else in the
system re-checks it, so a document marked `indexed` whose chunks carry no vector
is the silent failure doc 07 M5 forbids in its most expensive form — the customer
believes their price list is searchable, and discovers otherwise when a proposal
omits a price. `parsed` is the honest state for content that was stored,
classified and reviewable but never embedded, and this module returns it whenever
embedding did not fully succeed.

**Embedding is not a visibility decision.** Every chunk is embedded, including
the ones withheld to L5 by I4, because a vector does not make a chunk reachable —
the scope predicate does (I3). Withholding the vector as well would mean a chunk
approved in the review queue needed re-embedding before it could be found, so
approval would silently do half its job. `index_plan` therefore never reads and
never returns `scope` or `review_state`, and a test asserts the write statement
cannot change them.

**Partial success is refused.** If the embedder returns fewer vectors than there
are chunks, or vectors of the wrong width, the whole document stays `parsed`.
Writing the ones that worked would leave a document that is searchable in part,
with nothing to indicate which part.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.documents.chunk import Chunk
from app.embedding.contracts import (
    EmbeddedText,
    Embedder,
    EmbeddingAvailability,
    EmbeddingError,
)
from app.logging import get_logger

log = get_logger(__name__)

INDEXED = "indexed"
PARSED = "parsed"


@dataclass(frozen=True, slots=True)
class IndexPlan:
    """What to write, and what to tell the customer.

    `vectors` is either exactly as long as the chunk list or empty. There is no
    partial state, deliberately — see the module docstring.
    """

    vectors: tuple[EmbeddedText, ...]
    document_status: str
    message: str
    """Empty only when the document is fully searchable. Never a bare
    'something went wrong': it names the state and, where the customer can act,
    what would change it."""

    @property
    def searchable(self) -> bool:
        return self.document_status == INDEXED


def _not_searchable(reason: str, *, code: str, chunks: int) -> IndexPlan:
    """One un-searchable outcome, so every path reports the same shape.

    `code` is passed rather than derived from `reason`. The two carry different
    obligations: `reason` is customer-facing prose that should improve whenever
    someone finds better words, and `code` is a token a log query groups on. An
    earlier version inferred the code by substring-matching the prose, which meant
    rewording a sentence silently reclassified the event — the coupling the split
    exists to prevent.
    """
    log.info("document.not_embedded", chunks=chunks, reason_code=code)
    return IndexPlan(vectors=(), document_status=PARSED, message=reason)


def index_plan(chunks: list[Chunk], *, embedder: Embedder, expected_dim: int) -> IndexPlan:
    """Embed a document's chunks, or explain why the document is not searchable.

    Never raises. Every failure becomes a named state with a sentence attached,
    because the caller is a request handler whose job is to render the outcome
    rather than to catch it (I10 — never a zero, never a blank).
    """
    if not chunks:
        # Nothing to embed is not a failure: a parsed document with no extractable
        # text already failed visibly upstream in `parse_document`.
        return IndexPlan(vectors=(), document_status=PARSED, message="")

    status = embedder.status()
    if not status.usable:
        detail = status.detail
        if status.availability is EmbeddingAvailability.UNCONFIGURED:
            return _not_searchable(
                "Stored and reviewable, but not searchable: no embedding backend is "
                "configured. " + detail,
                code="unconfigured",
                chunks=len(chunks),
            )
        return _not_searchable(
            f"Stored and reviewable, but not searchable: {detail}",
            code=status.availability.value,
            chunks=len(chunks),
        )

    try:
        vectors = embedder.embed_passages([c.text for c in chunks])
    except EmbeddingError as exc:
        # Type only. These inputs are customer document content and the vendor
        # message can quote them; `app/logging.py` refuses content keys and this
        # keeps the same rule on a path it cannot police.
        log.warning("document.embedding_failed", error=type(exc).__name__, chunks=len(chunks))
        return _not_searchable(
            "Stored and reviewable, but not searchable: embedding failed. "
            "It will be retried; nothing was lost.",
            code="embedding_failed",
            chunks=len(chunks),
        )

    if len(vectors) != len(chunks):
        return _not_searchable(
            f"Stored and reviewable, but not searchable: the embedder returned "
            f"{len(vectors)} vectors for {len(chunks)} chunks, so the count does not match.",
            code="count_mismatch",
            chunks=len(chunks),
        )

    wrong = next((v for v in vectors if v.dim != expected_dim), None)
    if wrong is not None:
        # `EmbeddedText` already proves vector length equals its declared `dim`;
        # this catches a model whose width disagrees with the *column*, which is
        # a migration rather than a configuration change (ADR 0003).
        return _not_searchable(
            f"Stored and reviewable, but not searchable: {wrong.model_id} produces "
            f"{wrong.dim}-dimensional vectors and this database stores {expected_dim}.",
            code="dimension_mismatch",
            chunks=len(chunks),
        )

    log.info(
        "document.embedded",
        chunks=len(vectors),
        dim=expected_dim,
        model=vectors[0].model_id,
        backend=status.backend,
    )
    return IndexPlan(vectors=tuple(vectors), document_status=INDEXED, message="")
