"""Task 5.6 — what `indexed` is allowed to mean.

The claim under test is narrow and worth stating exactly: **a document says
`indexed` only when every one of its chunks carries a vector.** Before 5.6 the
upload route wrote `indexed` unconditionally, so the status was a promise nothing
kept — and the way a customer would have discovered it is a proposal silently
missing a price.

The second claim is the one I4 depends on: **embedding is not a visibility
decision.** Every chunk is embedded, including the ones withheld to L5, because a
vector does not make a chunk reachable — the scope predicate does. If withheld
chunks were left unembedded, approving one in the review queue would silently do
half its job.

Hermetic, like `test_document_upload.py`: the database write is captured rather
than performed, because what is under test is which status the route chooses and
what it hands to the INSERT. That the INSERT itself is accepted by Postgres is
proved separately, against a real database, in `test_chunk_embedding_roundtrip.py`
— a split this milestone learned the hard way, since substituting `_record`
concealed two constraint violations for a week.
"""

from __future__ import annotations

import io
from collections.abc import Iterator, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.deps import current_scope
from app.documents.chunk import Chunk
from app.documents.classify import ReviewState
from app.documents.index import INDEXED, PARSED, index_plan
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.embedding.contracts import (
    EmbeddedText,
    EmbedderStatus,
    EmbeddingAvailability,
    EmbeddingError,
)
from app.embedding.providers import DeterministicEmbedder, UnconfiguredEmbedder
from app.embedding.registry import get_embedder
from app.main import create_app

DIM = 1024
WORKSPACE = UUID("22222222-2222-2222-2222-222222222222")
USER = UUID("11111111-1111-1111-1111-111111111111")
CSRF = "a-known-csrf-value"


def chunks_for(*texts: str) -> list[Chunk]:
    return [
        Chunk(
            text=text,
            page_number=1,
            page_label=None,
            ordinal=index,
            char_start=0,
            char_end=len(text),
        )
        for index, text in enumerate(texts)
    ]


# ── Test embedders with specific defects ──────────────────────


class WrongWidthEmbedder(DeterministicEmbedder):
    """Reports the configured width but produces a different one.

    The realistic version of this is a model swap: `voyage-3` and
    `multilingual-e5-large` are both 1024, but `e5-base` is 768 and changing
    `NEXUS_EMBEDDING_MODEL_ID` alone would look like it worked.
    """

    def __init__(self, *, actual: int) -> None:
        super().__init__(dim=actual)


class ShortBatchEmbedder(DeterministicEmbedder):
    """Drops the last vector. A silently truncated batch would leave the tail of
    a document unsearchable inside a document marked searchable."""

    def embed_passages(self, texts: Sequence[str]) -> list[EmbeddedText]:
        return super().embed_passages(texts)[:-1]


class FailingEmbedder(DeterministicEmbedder):
    def embed_passages(self, texts: Sequence[str]) -> list[EmbeddedText]:
        raise EmbeddingError("RuntimeError while embedding")


class LoadedButUnusableEmbedder(UnconfiguredEmbedder):
    def status(self) -> EmbedderStatus:
        return EmbedderStatus(
            availability=EmbeddingAvailability.UNAVAILABLE,
            backend="fastembed",
            model_id="intfloat/multilingual-e5-large",
            dim=DIM,
            detail='fastembed is not installed — pip install -e ".[embeddings]"',
        )


# ── index_plan: the decision, without a route or a database ───


def test_a_working_embedder_makes_the_document_indexed() -> None:
    plan = index_plan(
        chunks_for("a", "b", "c"), embedder=DeterministicEmbedder(dim=DIM), expected_dim=DIM
    )

    assert plan.document_status == INDEXED
    assert plan.searchable is True
    assert len(plan.vectors) == 3
    assert plan.message == "", "a success carries no message"


def test_no_embedder_leaves_the_document_parsed_not_indexed() -> None:
    """The honest state for content that was stored but cannot be retrieved."""
    plan = index_plan(chunks_for("a", "b"), embedder=UnconfiguredEmbedder(), expected_dim=DIM)

    assert plan.document_status == PARSED
    assert plan.searchable is False
    assert plan.vectors == ()
    assert "not searchable" in plan.message


def test_the_message_says_what_would_make_it_searchable() -> None:
    """I10 — a named state, and where the customer can act, what to do."""
    plan = index_plan(chunks_for("a"), embedder=LoadedButUnusableEmbedder(), expected_dim=DIM)

    assert plan.document_status == PARSED
    assert "fastembed" in plan.message


def test_a_width_disagreement_names_both_numbers() -> None:
    plan = index_plan(chunks_for("a"), embedder=WrongWidthEmbedder(actual=768), expected_dim=DIM)

    assert plan.document_status == PARSED
    assert "768" in plan.message and "1024" in plan.message


def test_a_short_batch_is_refused_rather_than_partly_written() -> None:
    plan = index_plan(
        chunks_for("a", "b", "c"), embedder=ShortBatchEmbedder(dim=DIM), expected_dim=DIM
    )

    assert plan.document_status == PARSED
    assert plan.vectors == (), "writing the vectors that worked is the failure, not the fix"
    assert "2 vectors for 3 chunks" in plan.message


def test_an_embedder_that_raises_becomes_a_state_not_an_exception() -> None:
    """The caller is a request handler. Its job is to render the outcome."""
    plan = index_plan(chunks_for("a"), embedder=FailingEmbedder(dim=DIM), expected_dim=DIM)

    assert plan.document_status == PARSED
    assert "nothing was lost" in plan.message


def test_a_document_with_no_chunks_is_not_a_failure() -> None:
    plan = index_plan([], embedder=DeterministicEmbedder(dim=DIM), expected_dim=DIM)

    assert plan.document_status == PARSED
    assert plan.message == "", "the visible failure already happened in parse_document"


def test_vectors_carry_the_model_that_produced_them() -> None:
    """ADR 0003 — provenance per row, so a later model change knows what to
    re-embed without guessing."""
    plan = index_plan(chunks_for("a"), embedder=DeterministicEmbedder(dim=DIM), expected_dim=DIM)

    assert plan.vectors[0].model_id
    assert plan.vectors[0].dim == DIM


# ── The route ─────────────────────────────────────────────────


def scope_for(role: Role = Role.OWNER) -> ScopedSession:
    return ScopedSession(
        user_id=USER,
        workspace_id=WORKSPACE,
        tenant_id=uuid4(),
        role=role,
        departments=frozenset({Department.FINANCE}),
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[dict[str, Any]]]]:
    """A client whose writes are captured, with the embedder switchable per test."""
    recorded: list[dict[str, Any]] = []

    async def fake_record(**kwargs: Any) -> None:
        recorded.append(kwargs)

    class FakeStore:
        def put(self, key: str, data: bytes, *, content_type: str) -> None:
            return None

    monkeypatch.setattr("app.routes.documents._record", fake_record)
    monkeypatch.setattr("app.routes.documents._object_store", lambda settings: FakeStore())

    app = create_app()
    app.dependency_overrides[current_scope] = scope_for

    with TestClient(app) as c:
        c.cookies.set(CSRF_COOKIE_NAME, CSRF)
        yield c, recorded

    app.dependency_overrides.clear()


def upload(
    client: TestClient,
    *,
    content: bytes = b"Standard rate: OMR 3,200 per month.",
    filename: str = "prices.txt",
) -> Any:
    return client.post(
        "/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        data={"consent": "true"},
        headers={CSRF_HEADER_NAME: CSRF},
    )


def use_embedder(app_client: TestClient, embedder: Any) -> None:
    app_client.app.dependency_overrides[get_embedder] = lambda: embedder  # type: ignore[attr-defined]


def test_with_no_embedder_the_upload_reports_parsed_and_says_why(client) -> None:  # type: ignore[no-untyped-def]
    """The default state of a clean install: `NEXUS_EMBEDDING_BACKEND=none`."""
    c, _ = client
    body = upload(c).json()

    assert body["status"] == PARSED
    assert body["searchable"] is False
    assert body["chunks_embedded"] == 0
    assert body["message"], "an unsearchable document must never return an empty message"


def test_with_an_embedder_the_upload_reports_indexed(client) -> None:  # type: ignore[no-untyped-def]
    c, recorded = client
    use_embedder(c, DeterministicEmbedder(dim=DIM))

    body = upload(c).json()

    assert body["status"] == INDEXED
    assert body["searchable"] is True
    assert body["chunks_embedded"] > 0
    assert body["message"] == ""
    assert len(recorded[0]["vectors"]) == len(recorded[0]["chunks"])


def test_embedded_and_visible_are_reported_as_different_numbers(client) -> None:  # type: ignore[no-untyped-def]
    """I4 and searchability are orthogonal, and the response must not blur them.

    Today every chunk withholds — no classifier exists — so a fully embedded
    document is fully invisible. One number for both would read as "41 chunks are
    available to your team", which is false.
    """
    c, _ = client
    use_embedder(c, DeterministicEmbedder(dim=DIM))

    body = upload(c).json()

    assert body["chunks_embedded"] > 0
    assert body["chunks_indexed"] == 0
    assert body["chunks_held_for_review"] == body["chunks_embedded"]


def test_embedding_does_not_change_scope_or_review_state(client) -> None:  # type: ignore[no-untyped-def]
    """The I4 assertion. A vector is not a permission.

    If embedding promoted a chunk out of the review queue — or out of L5 — every
    withheld payroll chunk would become reachable the moment it was made
    searchable, which is precisely the silent workspace-wide breach doc 06 §3.3
    describes.
    """
    c, recorded = client
    use_embedder(c, DeterministicEmbedder(dim=DIM))

    upload(c)

    chunks = recorded[0]["chunks"]
    assert chunks
    for _, classification in chunks:
        assert classification.scope.name.startswith("L5")
        assert classification.review_state is ReviewState.NEEDS_REVIEW
        assert classification.owner_user_id == str(USER)


def test_a_failing_embedder_does_not_fail_the_upload(client) -> None:  # type: ignore[no-untyped-def]
    """The document is still the customer's document. Losing it because our
    embedder broke would lose something they believe they gave us."""
    c, recorded = client
    use_embedder(c, FailingEmbedder(dim=DIM))

    response = upload(c)

    assert response.status_code == 201
    assert response.json()["status"] == PARSED
    assert recorded[0]["chunks"], "the chunks are still stored"
    assert recorded[0]["vectors"] == ()


# ── Consent follows retention, not searchability ──────────────


def test_consent_is_recorded_whether_or_not_the_document_became_searchable(client) -> None:  # type: ignore[no-untyped-def]
    """The warranty was given for the bytes we now hold.

    `_record` used to stamp `consent_given_at` only on the `indexed` path, which was
    equivalent while `indexed` was written unconditionally. Now that a document can
    legitimately stop at `parsed`, tying the record of consent to searchability
    would leave retained customer content with no warranty attached to it —
    `ck_document_consent_before_indexing` would not complain, and the gap would only
    surface in a dispute.
    """
    c, recorded = client

    upload(c)  # no embedder -> parsed
    assert recorded[-1]["state"] == PARSED

    use_embedder(c, DeterministicEmbedder(dim=DIM))
    upload(c)  # embedder -> indexed
    assert recorded[-1]["state"] == INDEXED

    # `_record` computes the timestamp itself, so what this asserts is that both
    # paths reach it. The `failed` path below is the one that must not.
    assert len(recorded) == 2


def test_a_failed_parse_records_no_consent(client) -> None:  # type: ignore[no-untyped-def]
    """A document we could not read was never retained as content, so recording a
    warranty over it would overstate what happened."""
    c, recorded = client

    # The extension decides the parser, so a scan-shaped PDF needs a .pdf name —
    # these bytes under prices.txt parse perfectly well as text.
    upload(c, content=b"%PDF-1.4\n%empty\n", filename="scan.pdf")

    assert recorded[0]["state"] == "failed"


# ── The write refuses to be partial ───────────────────────────


async def test_record_refuses_a_vector_count_that_does_not_match() -> None:
    """The guard that makes `index_plan`'s promise checked rather than assumed.

    Raised before `scoped_connection` is opened, so this needs no database: the
    point is that a mismatched pair never reaches an INSERT at all.
    """
    from app.routes import documents

    with pytest.raises(RuntimeError, match="refusing a partial index"):
        await documents._record(
            document_id=uuid4(),
            scope=scope_for(),
            filename="prices.txt",
            content_type="text/plain",
            size_bytes=10,
            storage_key="k",
            digest="d",
            state=INDEXED,
            failure_reason=None,
            page_count=1,
            supersedes_id=None,
            chunks=[(chunks_for("a")[0], _withheld_classification())],
            vectors=tuple(DeterministicEmbedder(dim=DIM).embed_passages(["a", "b"])),
        )


def _withheld_classification() -> Any:
    from app.documents.classify import ClassificationInput, classify_chunk
    from app.domain.access import Sensitivity
    from app.domain.scopes import Scope

    return classify_chunk(
        ClassificationInput(
            text="a",
            suggested_scope=Scope.L5_PERSONAL,
            suggested_department=None,
            suggested_sensitivity=Sensitivity.NORMAL,
            confidence=0.0,
            classifier_failed=True,
        ),
        uploader_id=str(USER),
    )


# ── Nothing customer-shaped reaches a log ─────────────────────


def test_indexing_logs_no_document_content(  # type: ignore[no-untyped-def]
    client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`app/logging.py` refuses keys like `prompt`; chunk text has no such key to
    refuse, so the rule is kept by not passing it."""
    c, _ = client
    use_embedder(c, DeterministicEmbedder(dim=DIM))
    secret = "Standard rate: OMR 3,200 per month."

    with caplog.at_level("DEBUG"):
        upload(c, content=secret.encode())

    assert secret not in caplog.text
    assert "OMR" not in caplog.text
