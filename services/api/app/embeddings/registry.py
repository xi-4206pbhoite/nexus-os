"""Provider selection for embeddings. Configuration decides, not the caller.

Mirrors `app/ai/registry.py`, including the rule that absence never raises here:
the application must start and serve everything else when no embedding model is
installed.

One asymmetry with the AI registry is deliberate. There is no setting that can
select `DeterministicEmbedder`. Its vectors are hash-derived noise, so a
deployment that reached it would serve confident citations drawn from nothing,
with no visible symptom. Tests construct it directly instead.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache

from app.config import Settings, get_settings
from app.embeddings.contracts import Availability, Embedder, EmbedderStatus
from app.embeddings.providers import UnavailableEmbedder
from app.logging import get_logger

log = get_logger(__name__)


def _library_installed() -> bool:
    """Is `fastembed` importable, without importing it?

    `find_spec` avoids paying the import cost - and avoids loading a ~2GB model
    stack - just to answer a readiness probe.
    """
    return importlib.util.find_spec("fastembed") is not None


def build_embedder(settings: Settings) -> Embedder:
    if settings.embeddings_enabled is False:
        return UnavailableEmbedder(
            reason=Availability.DISABLED,
            detail="Semantic search is switched off in this environment.",
            model=settings.embedding_model_id,
            dimension=settings.embedding_dim,
        )

    if not _library_installed():
        return UnavailableEmbedder(
            model=settings.embedding_model_id,
            dimension=settings.embedding_dim,
        )

    # Imported here rather than at module scope so the library is only touched
    # when it is actually present.
    from app.embeddings.fastembed_provider import FastEmbedEmbedder

    return FastEmbedEmbedder(
        model_id=settings.embedding_model_id,
        dimension=settings.embedding_dim,
    )


@lru_cache
def get_embedder() -> Embedder:
    """The process-wide embedder.

    Cached because the model holds hundreds of megabytes of weights; one per
    request would exhaust memory. Tests clear this cache.
    """
    embedder = build_embedder(get_settings())
    status = embedder.status()
    log.info(
        "embeddings.provider.selected",
        provider=status.provider,
        model=status.model,
        availability=status.availability.value,
    )
    return embedder


def embedder_status() -> EmbedderStatus:
    """For `/health/ready` and any surface that renders search availability."""
    return get_embedder().status()
