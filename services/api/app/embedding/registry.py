"""Backend selection. The one place that decides which embedder runs.

Same argument as `app/ai/registry.py`: configuration decides, never the caller.
A module choosing its own embedder could choose the deterministic one in
production, and that failure is invisible — well-formed vectors with no meaning,
no error, no empty result.

Which is why this module does something `app/ai/registry.py` does not: it
**refuses** the test double outside local and CI. Not a warning in a log nobody
reads at 3am — `REFUSED`, from which every call raises.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import Env, Settings, get_settings
from app.embedding.contracts import Embedder, EmbedderStatus, EmbeddingAvailability
from app.embedding.providers import (
    DETERMINISTIC_BACKEND,
    DeterministicEmbedder,
    UnconfiguredEmbedder,
)
from app.logging import get_logger

log = get_logger(__name__)

FASTEMBED_BACKEND = "fastembed"
NONE_BACKEND = "none"

ENVIRONMENTS_ALLOWING_DETERMINISTIC = frozenset({Env.local, Env.ci})
"""Where a non-semantic embedder may run. Staging is excluded deliberately: it is
where a demo is given, and a demo over meaningless vectors is the fabricated
recommendation problem wearing a different hat."""


def build_embedder(settings: Settings) -> Embedder:
    """Choose an embedder from configuration.

    Never raises. An absent or unusable backend is a working object that answers
    honestly, so the application starts and the upload path can render the state
    rather than 500 on it.
    """
    backend = settings.embedding_backend.strip().lower()

    if backend in {"", NONE_BACKEND}:
        return UnconfiguredEmbedder(
            model_id=settings.embedding_model_id,
            dim=settings.embedding_dim,
        )

    if backend == DETERMINISTIC_BACKEND:
        if settings.env not in ENVIRONMENTS_ALLOWING_DETERMINISTIC:
            # Loud, and reported by /health/ready, because the alternative is a
            # workspace whose entire Brain is indexed with noise.
            log.error(
                "embedding.backend.refused",
                backend=backend,
                env=settings.env.value,
            )
            return UnconfiguredEmbedder(
                reason=EmbeddingAvailability.REFUSED,
                detail=(
                    f"The deterministic embedder produces non-semantic vectors and is "
                    f"not permitted in {settings.env.value}. Set "
                    f"NEXUS_EMBEDDING_BACKEND=fastembed."
                ),
                model_id=None,
                dim=settings.embedding_dim,
            )
        return DeterministicEmbedder(dim=settings.embedding_dim)

    if backend == FASTEMBED_BACKEND:
        # Imported here rather than at module scope so the optional dependency is
        # only touched when it is actually selected.
        from app.embedding.fastembed_provider import FastEmbedEmbedder

        return FastEmbedEmbedder(
            model_id=settings.embedding_model_id,
            dim=settings.embedding_dim,
            cache_dir=settings.model_cache_dir,
        )

    return UnconfiguredEmbedder(
        reason=EmbeddingAvailability.UNAVAILABLE,
        detail=f"Unknown embedding backend {backend!r}. Expected fastembed or none.",
        model_id=settings.embedding_model_id,
        dim=settings.embedding_dim,
    )


@lru_cache
def get_embedder() -> Embedder:
    """The process-wide embedder.

    Cached like `get_engine` and `get_provider`: a fastembed model holds an ONNX
    session and roughly 2 GB of resident memory once loaded, so one per request
    would be ruinous. Tests clear this cache.
    """
    embedder = build_embedder(get_settings())
    status = embedder.status()
    log.info(
        "embedding.backend.selected",
        backend=status.backend,
        model=status.model_id,
        dim=status.dim,
        availability=status.availability.value,
    )
    return embedder


def embedder_status() -> EmbedderStatus:
    """For `/health/ready` and any surface that renders searchability."""
    return get_embedder().status()
