"""The two non-model embedders: unconfigured, and deterministic for tests.

Neither pretends to understand text. That is the whole point of both of them.

`app/ai/providers.py` argues that a demo mode returning plausible analysis would
be the most damaging thing this codebase could contain. The retrieval equivalent
is subtler and therefore worse: an embedder that returns *well-formed, stable,
correctly-sized* vectors with no semantic structure. Every mechanism downstream
works. Vectors are stored, the ANN index builds, queries return the right number
of rows with plausible distances, and citations render. The results are noise.
Nothing fails, nothing is labelled, and the only symptom is that grounded answers
are subtly unhelpful.

So `DeterministicEmbedder` exists for tests and is *refused* outside local and CI
by `registry.py` — not merely discouraged in a docstring.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence

from app.embedding.contracts import (
    EmbeddedText,
    EmbedderStatus,
    EmbeddingAvailability,
    EmbeddingUnavailableError,
    as_passage,
    as_query,
)

# ── No embedder ───────────────────────────────────────────────


class UnconfiguredEmbedder:
    """What the application runs on until a backend is selected.

    Reports `UNCONFIGURED` and raises if called, exactly as
    `UnavailableProvider` does for the language model. Callers check `status()`
    and leave the document at `parsed` with a reason the customer can read;
    one that calls anyway has a bug worth surfacing loudly rather than a
    zero vector to paper over it.

    A zero vector would be the dangerous alternative: `vector(1024)` accepts it,
    the INSERT succeeds, and the document is marked searchable. Cosine distance
    to a zero vector is undefined, so pgvector would return NaN and the row would
    sort arbitrarily — a chunk that is present, ranked, citable and meaningless.
    """

    backend = "unconfigured"

    def __init__(
        self,
        *,
        reason: EmbeddingAvailability = EmbeddingAvailability.UNCONFIGURED,
        detail: str = "",
        model_id: str | None = None,
        dim: int | None = None,
    ) -> None:
        self._reason = reason
        self._detail = detail or _default_detail(reason)
        self._model_id = model_id
        self._dim = dim

    @property
    def model_id(self) -> str:
        raise EmbeddingUnavailableError("no embedder is configured; there is no model id")

    @property
    def dim(self) -> int:
        raise EmbeddingUnavailableError("no embedder is configured; there is no dimension")

    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=self._reason,
            backend=self.backend,
            model_id=self._model_id,
            dim=self._dim,
            detail=self._detail,
        )

    def embed_passages(self, texts: Sequence[str]) -> list[EmbeddedText]:
        raise EmbeddingUnavailableError(
            f"no embedder is available ({self._reason.value}); "
            f"{len(texts)} chunk(s) cannot be embedded"
        )

    def embed_query(self, text: str) -> EmbeddedText:
        raise EmbeddingUnavailableError(
            f"no embedder is available ({self._reason.value}); a query cannot be embedded"
        )


def _default_detail(reason: EmbeddingAvailability) -> str:
    return {
        EmbeddingAvailability.UNCONFIGURED: (
            "No embedding backend selected. Documents can be uploaded, parsed and "
            "reviewed; they will not become searchable until one is."
        ),
        EmbeddingAvailability.UNAVAILABLE: (
            "The embedding backend is selected but cannot run. Install the optional "
            'dependency with pip install -e ".[embeddings]".'
        ),
        EmbeddingAvailability.REFUSED: (
            "The configured embedding backend is not permitted in this environment."
        ),
        EmbeddingAvailability.AVAILABLE: "Available.",
    }[reason]


# ── Deterministic, for tests only ─────────────────────────────

DETERMINISTIC_BACKEND = "deterministic"


class DeterministicEmbedder:
    """Stable, correctly-sized vectors derived from a hash. **Not semantic.**

    Two properties make it useful, and one makes it dangerous.

    Useful: identical text always yields an identical vector, on any machine and
    in any process — so a test can assert that a chunk was embedded, that the
    provenance columns were written, and that a query vector round-trips through
    `vector(1024)`, without downloading 1.1 GB of weights into CI.

    Dangerous: nothing about the output signals that it is meaningless. Hence
    `model_id` carries the backend name, so a chunk embedded by it is
    identifiable and re-embeddable later — that is exactly what per-row
    `embedding_model_id` in migration 0007 is for — and `registry.py` refuses to
    build it outside local and CI.
    """

    backend = DETERMINISTIC_BACKEND

    def __init__(self, *, dim: int) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    @property
    def model_id(self) -> str:
        # Deliberately not the real model id. A row embedded by this must never
        # be mistaken for one embedded by e5, in a database or in a bug report.
        return f"{DETERMINISTIC_BACKEND}-sha256-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=EmbeddingAvailability.AVAILABLE,
            backend=self.backend,
            model_id=self.model_id,
            dim=self._dim,
            detail="Deterministic hash vectors. Not semantic — tests only.",
        )

    def embed_passages(self, texts: Sequence[str]) -> list[EmbeddedText]:
        # Prefixed here, like every other implementation, so a test that asserts
        # prefixing is testing the same rule production uses (ADR 0003).
        return [self._vector(as_passage(t)) for t in texts]

    def embed_query(self, text: str) -> EmbeddedText:
        return self._vector(as_query(text))

    def _vector(self, text: str) -> EmbeddedText:
        raw = _expand(text.encode("utf-8"), self._dim)
        norm = sum(x * x for x in raw) ** 0.5
        # A hash producing 1024 exact zeros is not reachable, but a zero vector
        # is undefined under cosine distance and would sort arbitrarily forever,
        # so it is refused rather than stored.
        if norm == 0.0:  # pragma: no cover - unreachable
            raise ValueError("degenerate zero vector")
        return EmbeddedText(
            vector=tuple(x / norm for x in raw),
            model_id=self.model_id,
            dim=self._dim,
        )


def _expand(seed: bytes, count: int) -> list[float]:
    """Counter-mode SHA-256 into `count` floats in [-1, 1).

    SHA-256 rather than `hash()`: the built-in is salted per process, so the same
    text would embed differently after a restart and a stored vector would stop
    matching its own query. Stability across processes is the one guarantee this
    class actually makes.
    """
    values: list[float] = []
    counter = 0
    while len(values) < count:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        # Eight 4-byte unsigned ints per digest, mapped onto [-1, 1).
        for (word,) in struct.iter_unpack(">I", digest):
            values.append(word / 2**31 - 1.0)
            if len(values) == count:
                break
        counter += 1
    return values
