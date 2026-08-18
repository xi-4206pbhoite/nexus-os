"""The embedding boundary.

Three guarantees, none visible from reading the code, so each is asserted:

1. **The application runs with no embedding model.** ADR 0003 chose a local
   model, which makes it a ~2GB download. Documents must still upload, parse and
   classify without it, with their chunks stored unembedded — a state migration
   0007's provenance constraint deliberately permits.

2. **Nothing invents a vector.** There is no demo mode. This matters more than
   the equivalent rule for generated text, because a fabricated embedding fails
   *invisibly*: it yields a ranked list of confident-looking citations next to a
   real answer, and nothing on the screen looks wrong.

3. **Document and query prefixes are not interchangeable.** E5 asymmetry is
   silent when broken — retrieval merely gets worse, which is indistinguishable
   from the product not being very good.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.embeddings.contracts import (
    Availability,
    Embedder,
    EmbeddingDimensionError,
    EmbeddingUnavailableError,
)
from app.embeddings.providers import DeterministicEmbedder, UnavailableEmbedder
from app.embeddings.registry import build_embedder
from app.main import create_app

# ── Running without a model ───────────────────────────────────


def test_no_library_selects_the_unavailable_embedder() -> None:
    embedder = build_embedder(Settings(embeddings_enabled=False))
    status = embedder.status()

    assert status.availability is Availability.DISABLED
    assert status.usable is False


def test_building_an_embedder_without_the_model_does_not_raise() -> None:
    """The distinction that matters: an absent embedding model is a supported
    operating state, not a misconfiguration."""
    build_embedder(Settings(embeddings_enabled=False))


def test_the_api_starts_and_serves_with_no_embedding_model() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


def test_readiness_reports_embeddings_separately_from_pgvector() -> None:
    """Folding these together would let "the extension is installed" read as
    "search works". They are independent, and only one of them decides whether
    an uploaded document can be found."""
    with TestClient(create_app()) as client:
        checks = {c["name"]: c for c in client.get("/health/ready").json()["checks"]}

    assert "embeddings" in checks
    assert "pgvector" in checks
    assert checks["embeddings"]["required_now"] is False, (
        "an absent embedding model must not take the service out of a load balancer"
    )


# ── Nothing invents a vector ──────────────────────────────────


def test_an_unavailable_embedder_refuses_rather_than_returning_zeros() -> None:
    """A zero vector would be accepted by the column and ranked by cosine
    distance like any other. Refusing is the only honest option."""
    embedder = UnavailableEmbedder()

    with pytest.raises(EmbeddingUnavailableError):
        embedder.embed_documents(["some text"])
    with pytest.raises(EmbeddingUnavailableError):
        embedder.embed_query("a question")


def test_an_unavailable_embedder_has_no_dimension() -> None:
    """Returning 1024 here would let a caller size a buffer or a column against
    a model that does not exist."""
    with pytest.raises(EmbeddingUnavailableError):
        _ = UnavailableEmbedder().dimension


def test_the_unavailable_detail_explains_what_still_works() -> None:
    """It reaches the UI, and almost everything does still work. A bare "not
    configured" would read as the upload having failed."""
    detail = UnavailableEmbedder().status().detail

    assert "upload" in detail.lower()
    assert "searchable" in detail.lower()


def test_no_setting_can_select_the_deterministic_embedder() -> None:
    """The asymmetry with the AI registry, and the reason for it.

    `ScriptedProvider` refuses unscripted skills, so a deployment reaching it
    fails loudly. Hash-derived vectors do not fail at all — they rank. So this
    provider must be unreachable from configuration entirely, and tests
    construct it directly.
    """
    for enabled in (True, False):
        embedder = build_embedder(Settings(embeddings_enabled=enabled))
        assert not isinstance(embedder, DeterministicEmbedder)


# ── The prefixes are not interchangeable ──────────────────────


def test_documents_and_queries_embed_differently() -> None:
    """If these matched, a caller could swap the two methods and no test would
    notice — which is exactly how the E5 prefixes get lost."""
    embedder = DeterministicEmbedder()
    same_text = "quarterly revenue by service"

    assert embedder.embed_documents([same_text])[0] != embedder.embed_query(same_text)


def test_the_only_module_naming_the_library_is_the_provider() -> None:
    """The claim that makes the model swappable, asserted rather than trusted.

    `registry.py` legitimately names it — selecting the implementation is its
    job. What must never happen is a route or a retrieval module importing it
    directly. `config.py` is exempt: it holds the model id, which is
    configuration rather than a library dependency.
    """
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = sorted(
        path.relative_to(app_dir).as_posix()
        for path in app_dir.rglob("*.py")
        if "fastembed" in path.read_text(encoding="utf-8").lower()
        and path.parent.name != "embeddings"
        and path.name != "config.py"
    )

    assert offenders == [], (
        f"the embedding library is named outside app/embeddings/: {offenders}. "
        "Depend on app.embeddings.contracts.Embedder instead."
    )


# ── Shape guarantees the schema depends on ────────────────────


def test_a_dimension_mismatch_is_refused_at_the_boundary() -> None:
    """`chunk.embedding` is `vector(1024)`. Catching this here names both
    numbers; catching it at the INSERT gives a driver type error, and not
    catching it at all means a widened column silently stores mixed widths that
    cosine distance will happily compare."""
    from app.embeddings.fastembed_provider import FastEmbedEmbedder

    embedder = FastEmbedEmbedder(model_id="stub", dimension=1024)
    embedder._model = _StubModel(width=768)

    with pytest.raises(EmbeddingDimensionError) as caught:
        embedder.embed_documents(["text"])

    assert "768" in str(caught.value) and "1024" in str(caught.value)


def test_a_short_result_is_refused_rather_than_zipped() -> None:
    """One vector short would misalign every subsequent chunk, so each citation
    would point at the wrong page — a wrong answer that looks sourced."""
    from app.embeddings.contracts import EmbeddingTransientError
    from app.embeddings.fastembed_provider import FastEmbedEmbedder

    embedder = FastEmbedEmbedder(model_id="stub", dimension=8)
    embedder._model = _StubModel(width=8, drop=1)

    with pytest.raises(EmbeddingTransientError):
        embedder.embed_documents(["a", "b", "c"])


def test_the_passage_prefix_reaches_the_model() -> None:
    """The prefix is applied inside the provider, so this is the only place it
    can be verified at all."""
    from app.embeddings.fastembed_provider import PASSAGE_PREFIX, FastEmbedEmbedder

    stub = _StubModel(width=8)
    embedder = FastEmbedEmbedder(model_id="stub", dimension=8)
    embedder._model = stub
    embedder.embed_documents(["revenue"])

    assert stub.seen == [PASSAGE_PREFIX + "revenue"]


def test_embedding_no_documents_does_not_call_the_model() -> None:
    embedder = DeterministicEmbedder()
    assert embedder.embed_documents([]) == []


def test_both_providers_satisfy_the_protocol() -> None:
    assert isinstance(DeterministicEmbedder(), Embedder)
    assert isinstance(UnavailableEmbedder(), Embedder)


class _StubModel:
    """Stands in for `fastembed.TextEmbedding` without the 2GB download."""

    def __init__(self, *, width: int, drop: int = 0) -> None:
        self.width = width
        self.drop = drop
        self.seen: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen = list(texts)
        out = [[0.1] * self.width for _ in texts]
        return out[: len(out) - self.drop] if self.drop else out
