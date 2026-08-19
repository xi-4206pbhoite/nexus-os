"""What the application is allowed to know about embeddings.

The shape follows `app/ai/contracts.py` on purpose — same availability-as-a-value
pattern, same "unconfigured is a normal state" reasoning — but one difference
matters enough to state before the code.

**An absent language model degrades a feature. An absent embedder degrades the
truth of a status column.** The product can serve every dashboard with no API
key (ADR 0011). It cannot make a document *searchable* without a vector, so a
document whose chunks were stored but never embedded is not `indexed`; it is
`parsed`. Calling it indexed would be the silent failure doc 07 M5 forbids: the
customer believes their price list is retrievable and finds out it was not when a
proposal omits it, which reads as the product being wrong rather than the upload
being incomplete.

So this interface answers three questions and no others: can you embed right now,
what would you produce, and what did you produce it with.

**Prefixes are not optional and not the caller's job.** `multilingual-e5` was
trained with `query: ` and `passage: ` markers; omitting them costs retrieval
quality quietly, with no error and no empty result to notice. There is therefore
no `embed(text)` on this protocol — only `embed_passages` for stored content and
`embed_query` for a search, each applying its own prefix internally (ADR 0003).

**No customer text is logged here.** `app/logging.py` refuses keys like `prompt`
and `input_snapshot`; the same rule applies to a chunk body. Telemetry from this
layer is counts, dimensions, model id and latency.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

# ── The e5 prefixes (ADR 0003) ────────────────────────────────

PASSAGE_PREFIX = "passage: "
"""Applied to content being stored and later retrieved."""

QUERY_PREFIX = "query: "
"""Applied to a search string. Asymmetric with the passage prefix by design:
the model was trained to place a question near the passages that answer it, not
near other questions."""


def as_passage(text: str) -> str:
    return f"{PASSAGE_PREFIX}{text}"


def as_query(text: str) -> str:
    return f"{QUERY_PREFIX}{text}"


# ── Availability ──────────────────────────────────────────────


class EmbeddingAvailability(StrEnum):
    """Why an embedder can or cannot be used, right now.

    Distinguished rather than collapsed into a boolean, for the same reason
    `app/ai/contracts.py` does it: each state has a different answer for the
    person reading the screen, and "the model weights are still downloading" is
    not "no embedder is configured".
    """

    AVAILABLE = "available"
    """Configured, loaded, and expected to work."""

    UNCONFIGURED = "unconfigured"
    """No backend selected. Documents can be uploaded, parsed, classified and
    reviewed; they cannot become searchable."""

    UNAVAILABLE = "unavailable"
    """A backend was selected but cannot run — the optional dependency is not
    installed, or the model weights could not be loaded."""

    REFUSED = "refused"
    """The configured backend is not permitted in this environment. Reserved for
    the deterministic test double, which must never run outside local and CI."""


@dataclass(frozen=True, slots=True)
class EmbedderStatus:
    availability: EmbeddingAvailability
    backend: str
    model_id: str | None
    dim: int | None
    detail: str
    """Safe to show a user. Never a path, a key or customer content."""

    @property
    def usable(self) -> bool:
        return self.availability is EmbeddingAvailability.AVAILABLE


# ── Result ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EmbeddedText:
    """One vector and the provenance that has to travel with it.

    `model_id` and `dim` are carried per vector rather than read from settings at
    write time. Settings describe what *would* be produced now; these describe
    what was actually produced, and migration 0007 stores both on the chunk row
    so a later model change can find what needs re-embedding without guessing
    (ADR 0003). Reading them from configuration at the point of the INSERT would
    mislabel every row written while a backend was mid-change.
    """

    vector: tuple[float, ...]
    model_id: str
    dim: int

    def __post_init__(self) -> None:
        if len(self.vector) != self.dim:
            raise EmbeddingDimensionError(
                f"vector has {len(self.vector)} dimensions but claims {self.dim}"
            )

    def to_sql_literal(self) -> str:
        """pgvector's text input format, for `CAST(:param AS vector)`.

        A method rather than a helper at the call site so every writer formats
        vectors identically. `repr` rather than a fixed number of decimals: the
        column is float4-backed and truncates on its own, but a `%.6f` in the
        caller would quietly zero every component smaller than 5e-7 — a
        normalised 1024-dimensional vector has plenty of those, and the loss
        would show up only as slightly wrong distances.
        """
        return "[" + ",".join(repr(float(x)) for x in self.vector) + "]"


# ── Errors ────────────────────────────────────────────────────


class EmbeddingError(Exception):
    """Base for embedder failures. Messages are safe to log, not to display."""


class EmbeddingUnavailableError(EmbeddingError):
    """Called an embedder that `status()` had already said was unusable.

    A bug rather than a runtime condition — check availability first, and render
    the honest state instead of calling.
    """


class EmbeddingDimensionError(EmbeddingError):
    """A vector's width does not match what the schema stores.

    Raised before any write. The `chunk.embedding` column is `vector(1024)`, so
    Postgres would reject a mismatch anyway — but it would do so with a message
    about a type, at the end of a transaction that has already written the
    document. Failing here names both numbers and the model that produced the
    wrong one.
    """


# ── The interface ─────────────────────────────────────────────


@runtime_checkable
class Embedder(Protocol):
    """What the application depends on. Implementations live beside this file.

    Note the absence of a general-purpose `embed`. Passages and queries are
    prefixed differently and the difference is invisible when wrong, so the only
    way to reach this layer is through a method that already knows which it is.
    """

    backend: str

    @property
    def model_id(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def status(self) -> EmbedderStatus:
        """Answer without loading a model or making a call. Safe per request."""
        ...

    def embed_passages(self, texts: Sequence[str]) -> list[EmbeddedText]:
        """Embed stored content. Order of the result matches the input.

        Batched because indexing a document is tens to hundreds of chunks and a
        per-chunk round trip through an ONNX session wastes most of the time in
        setup. Raises `EmbeddingError` or a subclass; never returns a short list.
        """
        ...

    def embed_query(self, text: str) -> EmbeddedText:
        """Embed a search string, with the query prefix rather than passage."""
        ...
