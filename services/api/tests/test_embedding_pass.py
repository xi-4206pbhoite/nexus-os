"""The embedding pass (task 5.6).

Hermetic: the database session is substituted, because what is under test is the
pass's decisions - refuse to invent, never widen scope, stay idempotent - not
whether Postgres accepts an UPDATE. The scoped-write behaviour these rows rely on
is proved against a real database in `test_tenant_isolation.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from app.documents.embed import embed_pending
from app.embeddings.contracts import EmbeddingError
from app.embeddings.providers import DeterministicEmbedder, UnavailableEmbedder


@dataclass
class _Row:
    id: Any
    content: str


class _FakeResult:
    def __init__(self, rows: list[_Row] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def all(self) -> list[_Row]:
        return self._rows


class _FakeSession:
    """Records every statement and its parameters."""

    def __init__(self, pending: list[_Row]) -> None:
        self._pending = pending
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        self.statements.append((sql, params or {}))
        if sql.strip().upper().startswith("SELECT"):
            return _FakeResult(rows=self._pending)
        return _FakeResult(rowcount=1)


def _pending(count: int = 3) -> list[_Row]:
    return [_Row(id=uuid4(), content=f"chunk text {i}") for i in range(count)]


# ── Nothing is invented ───────────────────────────────────────


async def test_no_model_does_no_work_and_is_not_an_error() -> None:
    """A scheduled job that raised here would log an error every run on a
    deployment configured exactly as intended."""
    session = _FakeSession(_pending())

    report = await embed_pending(session, UnavailableEmbedder())  # type: ignore[arg-type]

    assert report.embedded == 0
    assert report.failed == 0, "an absent model is not a failure"
    assert report.skipped_reason == "unconfigured"
    assert session.statements == [], "it must not even query when it cannot embed"


async def test_a_provider_error_fails_the_batch_without_writing() -> None:
    class _Broken(DeterministicEmbedder):
        def embed_documents(self, texts: Any) -> Any:
            raise EmbeddingError("boom")

    session = _FakeSession(_pending(2))
    report = await embed_pending(session, _Broken())  # type: ignore[arg-type]

    assert report.failed == 2
    assert report.embedded == 0
    assert not any("UPDATE" in sql for sql, _ in session.statements), (
        "a failed batch must write no vectors at all"
    )


async def test_the_error_message_is_not_logged_with_chunk_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Chunk text is customer content. An exception message can quote its input,
    so only the exception *type* is recorded.

    `capsys` rather than `caplog`: structlog renders to stdout, so caplog sees
    an empty string and the assertion would pass without proving anything.
    """

    class _Leaky(DeterministicEmbedder):
        def embed_documents(self, texts: Any) -> Any:
            raise EmbeddingError("failed on: Salaries by employee, Q3 payroll")

    session = _FakeSession([_Row(id=uuid4(), content="Salaries by employee")])
    await embed_pending(session, _Leaky())  # type: ignore[arg-type]

    output = capsys.readouterr().out
    assert "EmbeddingError" in output, "the failure must be recorded"
    assert "Salaries" not in output
    assert "payroll" not in output


# ── What it writes, and what it must not touch ────────────────


async def test_it_writes_the_vector_with_its_model_and_dimension() -> None:
    """Migration 0007's provenance constraint requires all three together: an
    embedding whose model is unrecorded cannot be re-embedded without guessing."""
    session = _FakeSession(_pending(2))
    embedder = DeterministicEmbedder(dimension=1024, model_id="test-model")

    report = await embed_pending(session, embedder)

    updates = [(sql, p) for sql, p in session.statements if "UPDATE" in sql]
    assert report.embedded == 2
    assert len(updates) == 2
    for _, params in updates:
        assert params["model"] == "test-model"
        assert params["dim"] == 1024
        assert params["embedding"].startswith("[") and params["embedding"].endswith("]")


async def test_it_never_touches_scope_or_review_state() -> None:
    """The pass that fills in vectors must not be able to promote a withheld
    chunk. There would be no review record of it if it could."""
    session = _FakeSession(_pending(1))

    await embed_pending(session, DeterministicEmbedder())

    for sql, _ in session.statements:
        if "UPDATE" not in sql:
            continue
        lowered = sql.lower()
        for forbidden in ("scope", "review_state", "sensitivity", "owner_user_id", "department"):
            assert forbidden not in lowered, f"the embedding pass must not write {forbidden}"


async def test_the_update_is_guarded_so_a_concurrent_pass_cannot_overwrite() -> None:
    """Two workers can select the same row. Without the guard the second would
    overwrite a vector from a possibly different model, leaving
    `embedding_model_id` correct only by luck."""
    session = _FakeSession(_pending(1))

    await embed_pending(session, DeterministicEmbedder())

    update = next(sql for sql, _ in session.statements if "UPDATE" in sql)
    assert "embedding IS NULL" in update


async def test_it_records_when_the_vector_was_produced() -> None:
    session = _FakeSession(_pending(1))

    await embed_pending(session, DeterministicEmbedder())

    update = next(sql for sql, _ in session.statements if "UPDATE" in sql)
    assert "embedded_at" in update


async def test_only_unembedded_non_empty_chunks_are_selected() -> None:
    session = _FakeSession(_pending(1))

    await embed_pending(session, DeterministicEmbedder())

    select = next(sql for sql, _ in session.statements if sql.strip().upper().startswith("SELECT"))
    assert "embedding IS NULL" in select
    assert "content <> ''" in select, "an empty chunk has nothing to embed"


async def test_nothing_pending_is_a_clean_no_op() -> None:
    session = _FakeSession([])

    report = await embed_pending(session, DeterministicEmbedder())

    assert (report.considered, report.embedded, report.failed) == (0, 0, 0)
    assert report.skipped_reason is None, "having nothing to do is not being skipped"
