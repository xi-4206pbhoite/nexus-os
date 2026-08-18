"""The only module that names an embedding library.

`test_embedding_boundary.py` asserts that, the same way `test_ai_boundary.py`
asserts it for the language-model vendor. Everything above depends on
`app.embeddings.contracts.Embedder`.

**The E5 prefixes are the reason this file is not three lines.** `multilingual-
e5-large` (ADR 0003) is trained with `passage:` on stored text and `query:` on
searches. Omit them and retrieval degrades; swap them and it degrades
differently. Neither raises, neither shows up in a unit test that only checks
vector width, and the symptom - slightly worse answers - is indistinguishable
from the product simply not being very good. So the prefixes live here, applied
in the two methods that cannot be confused for one another.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.embeddings.contracts import (
    Availability,
    EmbedderStatus,
    EmbeddingDimensionError,
    EmbeddingTransientError,
)
from app.logging import get_logger

log = get_logger(__name__)

PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "


class FastEmbedEmbedder:
    """Local embeddings via `fastembed`. No network at query time.

    ADR 0003 chose a local model so document text never leaves the deployment to
    be embedded. That is a data-protection property, not a performance one, and
    it is why an API-based embedder is not the fallback when this is missing -
    the fallback is honest unavailability.
    """

    def __init__(self, *, model_id: str, dimension: int) -> None:
        self._model_id = model_id
        self._dimension = dimension
        self._model: Any | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def _sdk(self) -> Any:
        """Load the library and weights on first use.

        Lazy for the same reason the language-model SDK is: importing at module
        scope would make `import app.main` depend on a ~2GB download, so a
        deployment without it could not start at all - and starting without it is
        a supported state.
        """
        if self._model is None:
            from fastembed import TextEmbedding

            try:
                self._model = TextEmbedding(model_name=self._model_id)
            except Exception as exc:
                # Weights may still be downloading, or disk may be full. Both
                # are worth retrying; neither should be reported as "no model
                # configured", which would be a different and wrong message.
                raise EmbeddingTransientError(type(exc).__name__) from exc
        return self._model

    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=Availability.AVAILABLE,
            provider="fastembed",
            model=self._model_id,
            dimension=self._dimension,
            detail="Local embedding model. Document text is not sent anywhere to be embedded.",
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors = [list(map(float, v)) for v in self._sdk().embed(texts)]

        if len(vectors) != len(texts):
            # Never return a short list: a caller zipping these against chunks
            # would attach the wrong vector to the wrong text, and every
            # citation downstream would point at the wrong page.
            raise EmbeddingTransientError(f"Embedded {len(vectors)} of {len(texts)} inputs.")

        for vector in vectors:
            if len(vector) != self._dimension:
                raise EmbeddingDimensionError(
                    f"Model {self._model_id} returned {len(vector)} dimensions,"
                    f" but the schema stores {self._dimension}."
                )
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed([PASSAGE_PREFIX + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([QUERY_PREFIX + text])[0]
