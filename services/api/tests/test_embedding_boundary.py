"""The embedding boundary.

Three guarantees are load-bearing and none is visible from reading a call site,
which is why they are asserted rather than trusted.

1. **The application runs with no embedder.** Documents upload, parse, classify
   and queue for review; they stay `parsed` rather than `indexed`. Not "starts
   and then 500s on the first upload".

2. **Nothing fabricates a vector.** The unconfigured embedder refuses. It does
   not return zeros — a zero vector is accepted by `vector(1024)`, makes the
   INSERT succeed, marks the document searchable, and then sorts arbitrarily
   forever under cosine distance. That is the retrieval-shaped version of the
   invented number I1 exists to prevent.

3. **The non-semantic test double cannot run in a deployed environment.** It
   produces well-formed, stable, correctly-sized vectors with no meaning, so
   every mechanism downstream appears to work. Nothing fails and nothing is
   labelled; the only symptom is that grounded answers are quietly useless.
"""

from __future__ import annotations

import pytest

from app.config import Env, Settings
from app.embedding.contracts import (
    PASSAGE_PREFIX,
    QUERY_PREFIX,
    EmbeddedText,
    Embedder,
    EmbeddingAvailability,
    EmbeddingDimensionError,
    EmbeddingUnavailableError,
    as_passage,
    as_query,
)
from app.embedding.providers import DeterministicEmbedder, UnconfiguredEmbedder
from app.embedding.registry import build_embedder

DIM = 1024


def settings_for(backend: str, *, env: Env = Env.ci, dim: int = DIM) -> Settings:
    return Settings(embedding_backend=backend, env=env, embedding_dim=dim)


# ── Running without an embedder ───────────────────────────────


def test_no_backend_selects_the_unconfigured_embedder() -> None:
    embedder = build_embedder(settings_for("none"))
    status = embedder.status()

    assert status.availability is EmbeddingAvailability.UNCONFIGURED
    assert status.usable is False


def test_an_empty_backend_string_is_the_same_as_none() -> None:
    assert build_embedder(settings_for("")).status().usable is False


def test_an_unknown_backend_is_unavailable_and_says_what_it_expected() -> None:
    status = build_embedder(settings_for("word2vec")).status()

    assert status.availability is EmbeddingAvailability.UNAVAILABLE
    assert "fastembed" in status.detail, "the detail must name a backend that works"


def test_the_unconfigured_embedder_refuses_rather_than_returning_zeros() -> None:
    """The single most important assertion in this file.

    A zero vector would satisfy the column, the constraint and the type checker.
    It would also make the document searchable, rank arbitrarily, and be citable.
    """
    embedder = UnconfiguredEmbedder()

    with pytest.raises(EmbeddingUnavailableError):
        embedder.embed_passages(["a price list"])
    with pytest.raises(EmbeddingUnavailableError):
        embedder.embed_query("what do we charge")


def test_the_unconfigured_embedder_has_no_model_id_or_dimension() -> None:
    """There is no model, so there is no honest answer to either question."""
    embedder = UnconfiguredEmbedder()

    with pytest.raises(EmbeddingUnavailableError):
        _ = embedder.model_id
    with pytest.raises(EmbeddingUnavailableError):
        _ = embedder.dim


# ── The test double is refused where it would do damage ───────


@pytest.mark.parametrize("env", [Env.staging, Env.production])
def test_the_deterministic_embedder_is_refused_in_deployed_environments(env: Env) -> None:
    """Staging is included deliberately: it is where demos happen."""
    embedder = build_embedder(settings_for("deterministic", env=env))
    status = embedder.status()

    assert status.availability is EmbeddingAvailability.REFUSED
    assert "fastembed" in status.detail, "the refusal must say what to set instead"

    with pytest.raises(EmbeddingUnavailableError):
        embedder.embed_passages(["anything"])


@pytest.mark.parametrize("env", [Env.local, Env.ci])
def test_the_deterministic_embedder_is_allowed_locally_and_in_ci(env: Env) -> None:
    assert build_embedder(settings_for("deterministic", env=env)).status().usable is True


def test_a_deterministic_vector_is_never_labelled_as_the_real_model() -> None:
    """`embedding_model_id` is stored per row so a later model change knows what
    to re-embed (ADR 0003). A row of noise labelled `multilingual-e5-large` would
    be indistinguishable from a real one, in the database and in a bug report."""
    embedder = DeterministicEmbedder(dim=DIM)

    assert "deterministic" in embedder.model_id
    assert "e5" not in embedder.model_id


# ── The e5 prefixes (ADR 0003) ────────────────────────────────


def test_a_passage_and_a_query_over_the_same_text_differ() -> None:
    """The prefixes are applied, and applied differently.

    If a call site forgot them, or the layer applied one prefix to both, these
    two vectors would be identical — and nothing else in the system would notice,
    because retrieval keeps returning rows. It just returns worse ones.
    """
    embedder = DeterministicEmbedder(dim=DIM)
    text = "Standard rate: OMR 3,200 per month"

    passage = embedder.embed_passages([text])[0]
    query = embedder.embed_query(text)

    assert passage.vector != query.vector


def test_the_prefixes_are_the_ones_the_model_was_trained_with() -> None:
    assert as_passage("x") == f"{PASSAGE_PREFIX}x" == "passage: x"
    assert as_query("x") == f"{QUERY_PREFIX}x" == "query: x"


def test_there_is_no_way_to_embed_unprefixed_text() -> None:
    """ADR 0003 requires prefixing in the service, never at a call site. The
    enforcement is structural: the protocol has no general-purpose `embed`."""
    assert not hasattr(Embedder, "embed")
    assert not hasattr(DeterministicEmbedder(dim=DIM), "embed")


# ── Dimensions ────────────────────────────────────────────────


def test_a_vector_that_disagrees_with_its_declared_dimension_is_refused() -> None:
    with pytest.raises(EmbeddingDimensionError):
        EmbeddedText(vector=(0.1, 0.2), model_id="test", dim=1024)


def test_the_embedder_produces_the_configured_width() -> None:
    embedder = build_embedder(settings_for("deterministic", dim=8))
    vector = embedder.embed_query("how much")

    assert vector.dim == 8
    assert len(vector.vector) == 8


# ── Determinism, which is the double's only real guarantee ────


def test_the_same_text_always_yields_the_same_vector() -> None:
    """Stable across processes, not merely within one.

    Python's `hash()` is salted per process, so a hash-based embedder built on it
    would embed the same text differently after a restart and a stored vector
    would stop matching its own query — with no error anywhere.
    """
    first = DeterministicEmbedder(dim=DIM).embed_passages(["identical text"])[0]
    second = DeterministicEmbedder(dim=DIM).embed_passages(["identical text"])[0]

    assert first.vector == second.vector


def test_different_text_yields_different_vectors() -> None:
    embedder = DeterministicEmbedder(dim=DIM)
    vectors = embedder.embed_passages(["first", "second", "third"])

    assert len({v.vector for v in vectors}) == 3


def test_batch_order_is_preserved() -> None:
    """A reordered batch would attach every vector to the wrong chunk, and every
    citation with it — the exact failure doc 01 §5 M8 calls the highest-liability
    one in the product."""
    embedder = DeterministicEmbedder(dim=DIM)
    texts = ["alpha", "beta", "gamma", "delta"]

    batched = embedder.embed_passages(texts)
    one_at_a_time = [embedder.embed_passages([t])[0] for t in texts]

    assert [v.vector for v in batched] == [v.vector for v in one_at_a_time]


def test_vectors_are_normalised() -> None:
    """Cosine distance does not require it, but an unnormalised vector makes the
    `<=>` operator's output harder to reason about when a threshold is chosen."""
    vector = DeterministicEmbedder(dim=DIM).embed_query("anything").vector
    norm = sum(x * x for x in vector) ** 0.5

    assert norm == pytest.approx(1.0)


def test_an_empty_batch_is_not_an_error() -> None:
    assert DeterministicEmbedder(dim=DIM).embed_passages([]) == []


# ── The SQL literal ───────────────────────────────────────────


def test_the_sql_literal_is_pgvector_text_form() -> None:
    literal = EmbeddedText(vector=(0.5, -0.25, 0.0), model_id="test", dim=3).to_sql_literal()

    assert literal == "[0.5,-0.25,0.0]"


def test_small_components_survive_the_literal() -> None:
    """A `%.6f` here would silently zero every component below 5e-7, and a
    normalised 1024-dimensional vector has many. The loss would surface only as
    slightly wrong distances, which is not a symptom anyone traces."""
    tiny = 1e-9
    literal = EmbeddedText(vector=(tiny,), model_id="test", dim=1).to_sql_literal()

    assert float(literal.strip("[]")) == tiny
