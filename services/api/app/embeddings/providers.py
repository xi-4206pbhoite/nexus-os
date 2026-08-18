"""Providers that need no model installed.

`UnavailableEmbedder` is what runs before anyone installs the weights, and it is
a working object rather than a null: it answers `status()` honestly and refuses
to embed. `DeterministicEmbedder` exists for tests and must never leave them.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence

from app.embeddings.contracts import (
    Availability,
    EmbedderStatus,
    EmbeddingUnavailableError,
)

UNAVAILABLE_DETAIL = (
    "Semantic search is not set up. Documents still upload, parse and classify;"
    " their text is stored and will be searchable once the embedding model is"
    " installed."
)


class UnavailableEmbedder:
    """No model installed. Says so, and refuses to invent one.

    The detail string is written for a user rather than an operator, because it
    reaches the UI: it has to explain what still works, since almost everything
    does. Only search is affected.
    """

    def __init__(
        self,
        *,
        reason: Availability = Availability.UNCONFIGURED,
        detail: str = UNAVAILABLE_DETAIL,
        model: str | None = None,
        dimension: int | None = None,
    ) -> None:
        self._reason = reason
        self._detail = detail
        self._model = model
        self._dimension = dimension

    @property
    def model_id(self) -> str:
        return "unavailable"

    @property
    def dimension(self) -> int:
        # Not a plausible default. A caller that reads this to size a buffer or
        # a column should fail rather than silently agree with 1024.
        raise EmbeddingUnavailableError("No embedding model is installed, so it has no dimension.")

    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=self._reason,
            provider="unavailable",
            model=self._model,
            dimension=self._dimension,
            detail=self._detail,
        )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingUnavailableError(UNAVAILABLE_DETAIL)

    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingUnavailableError(UNAVAILABLE_DETAIL)


class DeterministicEmbedder:
    """A test double. **Not a demo mode, and not semantic.**

    Hash-derived vectors are stable and let tests assert plumbing - that a
    vector of the right width reaches the right column with the right model id,
    that supersession re-embeds, that a dimension mismatch is caught. They carry
    no meaning whatsoever: two paraphrases land as far apart as two unrelated
    sentences.

    That is why the registry never returns this and no setting selects it. Tests
    construct it directly. If it were ever reachable from configuration, a
    misconfigured deployment would serve confident citations drawn from noise,
    and nothing on the screen would look wrong - the failure ADR 0011 forbids
    for generated text, which is strictly harder to notice for a ranked list.
    """

    def __init__(self, *, dimension: int = 1024, model_id: str = "deterministic-test") -> None:
        self._dimension = dimension
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=Availability.AVAILABLE,
            provider="deterministic-test",
            model=self._model_id,
            dimension=self._dimension,
            detail="Deterministic test embedder. Not semantic; never for production use.",
        )

    def _vector(self, text: str) -> list[float]:
        """A unit vector derived from the text's digest.

        Unit length because cosine distance on a zero or unnormalised vector
        behaves differently from the real thing, and a test that passes only
        because its vectors are degenerate proves nothing about the query.
        """
        out: list[float] = []
        counter = 0
        while len(out) < self._dimension:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            # 8 floats per digest, each in [-1, 1).
            for i in range(0, 32, 4):
                (raw,) = struct.unpack(">I", digest[i : i + 4])
                out.append(raw / 2**31 - 1.0)
            counter += 1
        out = out[: self._dimension]
        norm = sum(x * x for x in out) ** 0.5 or 1.0
        return [x / norm for x in out]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(f"passage:{t}") for t in texts]

    def embed_query(self, text: str) -> list[float]:
        # Prefixed differently from documents, mirroring E5, so a test that
        # accidentally swaps the two methods fails instead of passing.
        return self._vector(f"query:{text}")
