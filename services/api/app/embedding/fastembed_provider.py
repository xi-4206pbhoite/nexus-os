"""`multilingual-e5-large` via fastembed, in-process on CPU (ADR 0003).

Imported lazily by `registry.py`, the same arrangement `app/ai/` uses for its own
optional SDK: `fastembed` is an optional dependency, so nothing here may be
touched at application import time. `import app.main` must not require it.

Three ADR 0003 consequences are implemented rather than commented:

- **Weights are ~1.1 GB and download on first use**, to `settings.model_cache_dir`
  (gitignored). The download happens on the first `embed_*` call, never at
  construction, so `status()` stays a cheap synchronous answer that a readiness
  probe can call per request. A model that downloads during a health check would
  make the first probe after a deploy time out.
- **The dimension is verified against configuration**, because the `chunk.embedding`
  column is fixed at `vector(1024)` by migration 0007. A model returning 768
  fails here, naming both numbers, rather than at the INSERT naming a type.
- **Prefixes are applied by the base class contract**, never by a caller.

This runs on CPU and is slower than a hosted API. That cost lands on a background
indexing step and never between a customer and their upload confirmation.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.embedding.contracts import (
    EmbeddedText,
    EmbedderStatus,
    EmbeddingAvailability,
    EmbeddingDimensionError,
    EmbeddingError,
    as_passage,
    as_query,
)
from app.logging import get_logger

log = get_logger(__name__)

BACKEND = "fastembed"


class FastEmbedEmbedder:
    """A lazily-loaded ONNX embedding model.

    `status()` reports `AVAILABLE` once the package imports, before the weights
    are on disk. That is the honest answer to the question it is asked — "can
    this backend embed?" — and the alternative, reporting unavailable until a
    1.1 GB download finishes, would make a first deploy look broken.
    """

    backend = BACKEND

    def __init__(self, *, model_id: str, dim: int, cache_dir: Path) -> None:
        self._model_id = model_id
        self._dim = dim
        self._cache_dir = cache_dir
        self._model: Any | None = None

    @property
    def model_id(self) -> str:
        """The model name **and the library version that ran it.**

        Not decoration. fastembed 0.8.0 embeds `multilingual-e5-large` with mean
        pooling where 0.5.1 used the CLS token — different vectors, identical
        model name, and it says so only in a `UserWarning` at load time. ADR 0003
        stores this per chunk row precisely so a future migration can identify
        what needs re-embedding without guessing, and the model name alone cannot:
        two rows written months apart could be mutually unsearchable while
        claiming the same provenance.

        Vectors from different pooling strategies do not share a space, so mixing
        them silently degrades retrieval rather than failing.
        """
        return f"{self._model_id}@fastembed-{_fastembed_version()}"

    @property
    def dim(self) -> int:
        return self._dim

    def status(self) -> EmbedderStatus:
        available = _fastembed_importable()
        return EmbedderStatus(
            availability=(
                EmbeddingAvailability.AVAILABLE if available else EmbeddingAvailability.UNAVAILABLE
            ),
            backend=self.backend,
            model_id=self._model_id,
            dim=self._dim,
            detail=(
                "Local CPU model. Weights are downloaded on first use."
                if available
                else 'fastembed is not installed — pip install -e ".[embeddings]"'
            ),
        )

    def embed_passages(self, texts: Sequence[str]) -> list[EmbeddedText]:
        if not texts:
            return []
        return self._embed([as_passage(t) for t in texts])

    def embed_query(self, text: str) -> EmbeddedText:
        return self._embed([as_query(text)])[0]

    # ── Internals ─────────────────────────────────────────────

    def _load(self) -> Any:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise EmbeddingError(
                    'fastembed is not installed. pip install -e ".[embeddings]"'
                ) from exc

            self._cache_dir.mkdir(parents=True, exist_ok=True)
            log.info("embedding.model.loading", model=self._model_id, backend=self.backend)
            self._model = TextEmbedding(model_name=self._model_id, cache_dir=str(self._cache_dir))
        return self._model

    def _embed(self, prefixed: list[str]) -> list[EmbeddedText]:
        model = self._load()
        try:
            raw = list(model.embed(prefixed))
        except Exception as exc:
            # The message is logged, never displayed, and deliberately carries no
            # input: these strings are customer document content.
            raise EmbeddingError(f"{type(exc).__name__} while embedding") from exc

        if len(raw) != len(prefixed):
            raise EmbeddingError(f"embedder returned {len(raw)} vectors for {len(prefixed)} inputs")

        # Resolved once: it is the same for every vector in the batch, and it is
        # `self.model_id` rather than `self._model_id` deliberately — the versioned
        # form is what gets persisted, which is the entire point of carrying it.
        provenance = self.model_id

        out: list[EmbeddedText] = []
        for vector in raw:
            values = tuple(float(x) for x in vector)
            if len(values) != self._dim:
                raise EmbeddingDimensionError(
                    f"{self._model_id} produced {len(values)} dimensions but "
                    f"chunk.embedding is vector({self._dim}); re-embedding is a "
                    "migration, not a configuration change (ADR 0003)"
                )
            out.append(EmbeddedText(vector=values, model_id=provenance, dim=self._dim))

        log.info("embedding.batch", backend=self.backend, count=len(out), dim=self._dim)
        return out


def _fastembed_version() -> str:
    """The installed fastembed version, or `unknown` if it cannot be determined.

    Never raises: this is called to *label* a vector, and failing to label one is
    not a reason to refuse to produce it.
    """
    try:
        from importlib.metadata import version

        return version("fastembed")
    except Exception:  # pragma: no cover - defensive
        return "unknown"


def _fastembed_importable() -> bool:
    from importlib.util import find_spec

    try:
        return find_spec("fastembed") is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False
