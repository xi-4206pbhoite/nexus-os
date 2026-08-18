"""Task 5.6 - the embedding pass.

**Deliberately not inline in the upload.** `app/routes/documents.py` says why:
embedding is slow and needs a ~2GB model, and it must not sit between the
customer and their upload confirmation. So chunks are written with a NULL
embedding - a state migration 0007's `ck_chunk_embedding_provenance` permits -
and this pass fills them in afterwards.

Three properties are worth stating because each is a decision rather than an
implementation detail.

**A chunk with no embedding is honest, not broken.** It exists, it is
classified, it is in the review queue if it needs to be, and it is not
searchable yet. The alternative - refusing the upload until a model is installed
- would make an optional capability into a hard dependency, which ADR 0011 and
ADR 0003 both reject.

**This pass runs unscoped, and that is safe only because it never reads content
across a boundary to *answer* anything.** It selects chunks by embedding
nullity, embeds their text, and writes the vector back to the same row. It makes
no cross-workspace comparison and returns no content. Retrieval - the path that
answers questions - stays scoped through `ScopedSession` (I2/I3). Doing this
sweep per workspace would mean reloading the model's working set per tenant for
no isolation gain.

**Scope fields are already on the row** (doc 06 §12, task 5.6's own wording), so
this pass never has to reconstruct them. It writes only the three embedding
columns. That matters because a pass that also touched `scope` could silently
promote a withheld chunk, and there would be no review record of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.contracts import (
    Embedder,
    EmbeddingError,
    EmbeddingUnavailableError,
)
from app.logging import get_logger

log = get_logger(__name__)

DEFAULT_BATCH = 32
"""Small. Each batch is one model call and one UPDATE round trip, and a failure
costs the batch rather than the pass."""


@dataclass(frozen=True, slots=True)
class EmbeddingReport:
    considered: int
    embedded: int
    failed: int
    skipped_reason: str | None = None
    """Set when the pass did no work for a reason that is not an error - almost
    always "no embedding model installed". Distinguished from `failed` because
    an operator should not be paged for a supported configuration."""


_SELECT_PENDING = text(
    "SELECT id, content FROM chunk"
    " WHERE embedding IS NULL AND content <> ''"
    " ORDER BY created_at"
    " LIMIT :limit"
)

_UPDATE_EMBEDDING = text(
    "UPDATE chunk"
    " SET embedding = CAST(:embedding AS vector),"
    "     embedding_model_id = :model,"
    "     embedding_dim = :dim,"
    "     embedded_at = now()"
    " WHERE id = :id AND embedding IS NULL"
)
"""The `embedding IS NULL` guard makes this idempotent under a concurrent pass.

Two workers that selected the same row would otherwise both write, and the
second would overwrite a vector from a possibly different model while leaving
`embedding_model_id` consistent only by luck.
"""


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


async def embed_pending(
    db: AsyncSession,
    embedder: Embedder,
    *,
    limit: int = DEFAULT_BATCH,
) -> EmbeddingReport:
    """Embed up to `limit` chunks that have no vector yet.

    Returns a report rather than raising on an unavailable model: absence is a
    supported state and a scheduled job that raised on it would log an error
    every time it ran on a deployment that is working exactly as configured.
    """
    status = embedder.status()
    if not status.usable:
        return EmbeddingReport(
            considered=0,
            embedded=0,
            failed=0,
            skipped_reason=status.availability.value,
        )

    rows = (await db.execute(_SELECT_PENDING, {"limit": limit})).all()
    if not rows:
        return EmbeddingReport(considered=0, embedded=0, failed=0)

    texts = [str(row.content) for row in rows]

    try:
        vectors = embedder.embed_documents(texts)
    except EmbeddingUnavailableError:
        # The model went away between `status()` and the call - a race, not a
        # failure worth counting against the chunks.
        return EmbeddingReport(
            considered=len(rows), embedded=0, failed=0, skipped_reason="unconfigured"
        )
    except EmbeddingError as exc:
        # Type only. Chunk text is customer content and must not reach a log
        # line (app/logging.py enforces this for known keys; this is the same
        # rule applied by hand to an exception message that could quote input).
        log.warning("embeddings.batch_failed", error=type(exc).__name__, count=len(rows))
        return EmbeddingReport(considered=len(rows), embedded=0, failed=len(rows))

    embedded = 0
    for row, vector in zip(rows, vectors, strict=True):
        # `rowcount` is the whole point of the guarded UPDATE: 0 means another
        # pass got there first, which is success, not a write.
        result = cast(
            "CursorResult[Any]",
            await db.execute(
                _UPDATE_EMBEDDING,
                {
                    "id": str(row.id),
                    "embedding": _vector_literal(vector),
                    "model": embedder.model_id,
                    "dim": embedder.dimension,
                },
            ),
        )
        embedded += result.rowcount or 0

    log.info(
        "embeddings.pass_complete",
        considered=len(rows),
        embedded=embedded,
        model=status.model,
    )
    return EmbeddingReport(considered=len(rows), embedded=embedded, failed=0)
