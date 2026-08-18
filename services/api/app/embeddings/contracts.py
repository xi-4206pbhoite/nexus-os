"""The embedding boundary: what the rest of the application may know.

Nothing outside `app/embeddings/` imports an embedding library, exactly as
nothing outside `app/ai/` imports a language-model SDK (ADR 0011). Everything
above this file depends on `Embedder`.

Four decisions shape this interface. Each is a product constraint, not a style
preference.

**Unavailable is a value, not an exception.** The embedding model is a ~2GB
download (ADR 0003). A workspace that has not installed it is in a normal
operating state: documents still upload, parse, classify and land in the review
queue, and their chunks are stored with a NULL embedding. They are simply not
yet searchable, and the product must say so. Migration 0007's
`ck_chunk_embedding_provenance` already permits that state and forbids the
dishonest one — an embedding without a recorded model.

**A fabricated embedding is worse than none.** This is ADR 0011's rule applied
to vectors, and it is sharper here because the failure is invisible. A random or
hash-derived vector produces a *ranked list of confident-looking citations* that
carries no semantic meaning at all. There is no labelling that survives it: the
citations appear next to a real answer, and the screenshot shows a working
product. So there is no demo mode, and `DeterministicEmbedder` exists only for
tests and is never returned by the registry.

**Documents and queries are embedded differently, and getting it wrong fails
silently.** E5 models are trained with asymmetric prefixes - `passage:` for
stored text, `query:` for a search - and omitting them, or swapping them, does
not raise. It just retrieves worse. A single `embed()` would make that mistake
easy to write and impossible to see, so the two are separate methods and the
prefix is applied inside the provider rather than by callers.

**Dimension is checked, never assumed.** The `chunk.embedding` column is
`vector(1024)`. A provider returning 768 must fail at the boundary with a
message naming both numbers, rather than at the INSERT with a type error, or -
worst - being written successfully after somebody widens the column.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

# ── Availability ──────────────────────────────────────────────


class Availability(StrEnum):
    """Why an embedder can or cannot be used, right now.

    Deliberately a separate enum from `app.ai.contracts.Availability` rather
    than a shared import. The two boundaries are independent: a workspace can
    have a language model and no embedding model, or the reverse, and coupling
    the packages so one imports the other's vocabulary would make that
    relationship look closer than it is.
    """

    AVAILABLE = "available"
    """Installed and expected to work."""

    UNCONFIGURED = "unconfigured"
    """The library or model weights are not installed. The normal initial state."""

    DISABLED = "disabled"
    """Switched off deliberately for this environment."""


@dataclass(frozen=True, slots=True)
class EmbedderStatus:
    availability: Availability
    provider: str
    model: str | None
    dimension: int | None
    detail: str
    """Safe to show a user. Never contains a path, a key or customer content."""

    @property
    def usable(self) -> bool:
        return self.availability is Availability.AVAILABLE


# ── Errors ────────────────────────────────────────────────────


class EmbeddingError(Exception):
    """Base class. Callers that must not fail on embedding catch this."""


class EmbeddingUnavailableError(EmbeddingError):
    """Raised when an unavailable embedder is asked to embed anyway.

    Reaching this means a caller ignored `status()`. It is a programming error
    surfaced loudly, not a runtime condition to be papered over: the alternative
    is inventing a vector.
    """


class EmbeddingDimensionError(EmbeddingError):
    """A provider returned vectors of the wrong width for the schema."""


class EmbeddingTransientError(EmbeddingError):
    """A retryable failure - the model is loading, or resources are exhausted."""


# ── The interface ─────────────────────────────────────────────


@runtime_checkable
class Embedder(Protocol):
    """The only embedding contract the application depends on."""

    @property
    def model_id(self) -> str:
        """Recorded on every row, so re-embedding never has to guess.

        Migration 0007 stores this per chunk precisely so two models can coexist
        during a migration and a later pass can find the stale rows.
        """
        ...

    @property
    def dimension(self) -> int: ...

    def status(self) -> EmbedderStatus:
        """Answerable without embedding anything, and without network access."""
        ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed text for storage. Applies the model's passage prefix.

        Returns one vector per input, in order. Raises rather than returning a
        short list: a caller zipping vectors against chunks would otherwise
        attach the wrong embedding to the wrong text.
        """
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query. Applies the model's query prefix."""
        ...
