"""The vector actually reaches Postgres, and the predicate rides with the query.

Task 5.6's hermetic tests prove the route picks the right status and hands the
right values to the INSERT. They cannot prove Postgres *accepts* it, and that gap
is not theoretical: substituting `_record` concealed two constraint violations on
this exact path — `review_state = 'needs_review'` against a CHECK that allows
`pending_review`, and `status = 'superseded'` against one that allowed neither.
Both would have failed every real insert while the whole suite stayed green.

So this suite writes real chunks, with real vectors, as the real application role,
and then asks the question M6 is built on: **does a scope predicate combine with
an ANN ordering in one query?** (I3 — filter before search, never after.)

Runs against a real PostgreSQL with pgvector, as `nexus_app`. Skips loudly
without one, because a silent pass here would be worse than no test.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, create_engine

from app.documents.classify import ReviewState
from app.embedding.providers import DeterministicEmbedder
from tests.dburl import database_url

DB_URL = database_url()
requires_db = pytest.mark.skipif(
    DB_URL is None,
    reason="No NEXUS_DATABASE_URL — the embedding round trip needs a real PostgreSQL",
)

DIM = 1024


@pytest.fixture(scope="module")
def engine():  # type: ignore[no-untyped-def]
    if DB_URL is None:
        pytest.skip("no database")
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine) -> Iterator[Connection]:  # type: ignore[no-untyped-def]
    """Always rolled back: this suite writes customer-shaped rows."""
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def set_scope(conn: Connection, workspace_id: UUID, user_id: UUID) -> None:
    conn.execute(
        sa.text(
            "SELECT set_config('nexus.workspace_id', :ws, true),"
            "       set_config('nexus.user_id', :u, true)"
        ),
        {"ws": str(workspace_id), "u": str(user_id)},
    )


@pytest.fixture
def workspace(conn: Connection) -> tuple[UUID, UUID, UUID]:
    """A workspace, a user, and a consented document to hang chunks off."""
    tenant, ws, user, doc = uuid4(), uuid4(), uuid4(), uuid4()

    conn.execute(
        sa.text("INSERT INTO tenant (id, name) VALUES (:t, 'Embedding Tenant')"),
        {"t": str(tenant)},
    )
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(user), "e": f"embed-{user}@example.test"},
    )
    set_scope(conn, ws, user)
    conn.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name)"
            " VALUES (:id, :id, :t, 'Embedding Workspace')"
        ),
        {"id": str(ws), "t": str(tenant)},
    )
    conn.execute(
        sa.text("INSERT INTO membership (workspace_id, user_id, role) VALUES (:ws, :u, 'owner')"),
        {"ws": str(ws), "u": str(user)},
    )
    conn.execute(
        sa.text(
            "INSERT INTO document"
            " (id, workspace_id, uploaded_by_user_id, filename, content_type, size_bytes,"
            "  storage_key, content_sha256, status, consent_given_at, consent_text_version)"
            " VALUES (:d, :ws, :u, 'prices.txt', 'text/plain', 10, 'k', 'sha', 'indexed',"
            "         now(), 'test.v1')"
        ),
        {"d": str(doc), "ws": str(ws), "u": str(user)},
    )
    return ws, user, doc


def insert_chunk(
    conn: Connection,
    *,
    workspace_id: UUID,
    document_id: UUID,
    ordinal: int,
    text: str,
    scope: str,
    owner_user_id: UUID | None,
    department: list[str] | None = None,
    review_state: str = ReviewState.NEEDS_REVIEW.value,
) -> UUID:
    """Write a chunk exactly as `app/routes/documents.py` does.

    Deliberately mirrors the production statement, including the vector cast and
    the provenance columns, so a divergence between this and the route shows up
    here rather than in a customer's workspace.
    """
    vector = DeterministicEmbedder(dim=DIM).embed_passages([text])[0]
    return UUID(
        str(
            conn.execute(
                sa.text(
                    "INSERT INTO chunk"
                    " (workspace_id, document_id, source_page, source_label, ordinal, content,"
                    "  token_estimate, scope, department, owner_user_id, sensitivity,"
                    "  classified_by, confidence, review_state,"
                    "  embedding, embedding_model_id, embedding_dim, embedded_at)"
                    " VALUES (:ws, :doc, 1, NULL, :ordinal, :content, 4, :scope,"
                    "         :department, :owner, 'normal', 'rules-v1:classifier-failed', 0.0,"
                    "         :review, CAST(:embedding AS vector), :model, :dim, now())"
                    " RETURNING id"
                ),
                {
                    "ws": str(workspace_id),
                    "doc": str(document_id),
                    "ordinal": ordinal,
                    "content": text,
                    "scope": scope,
                    "department": department or [],
                    "owner": str(owner_user_id) if owner_user_id else None,
                    "review": review_state,
                    "embedding": vector.to_sql_literal(),
                    "model": vector.model_id,
                    "dim": vector.dim,
                },
            ).scalar_one()
        )
    )


# ── The insert the hermetic suite cannot check ────────────────


@requires_db
def test_a_withheld_chunk_with_a_vector_is_accepted(
    conn: Connection, workspace: tuple[UUID, UUID, UUID]
) -> None:
    """The exact row the upload route writes today: L5, pending review, embedded.

    Every value comes from production code — `ReviewState.NEEDS_REVIEW.value` and
    `EmbeddedText.to_sql_literal()` — so a spelling that a CHECK constraint
    rejects fails here instead of silently in a deployment.
    """
    ws, user, doc = workspace

    chunk_id = insert_chunk(
        conn,
        workspace_id=ws,
        document_id=doc,
        ordinal=0,
        text="Standard rate: OMR 3,200 per month",
        scope="L5",
        owner_user_id=user,
    )

    row = conn.execute(
        sa.text(
            "SELECT review_state, embedding_dim, embedding_model_id,"
            "       embedded_at IS NOT NULL AS stamped,"
            "       vector_dims(embedding) AS dims"
            " FROM chunk WHERE id = :id"
        ),
        {"id": str(chunk_id)},
    ).one()

    assert row.review_state == ReviewState.NEEDS_REVIEW.value
    assert row.dims == DIM, "the vector round-tripped at full width"
    assert row.embedding_dim == DIM
    assert row.embedding_model_id
    assert row.stamped is True


@requires_db
def test_every_review_state_the_enum_can_produce_is_accepted(
    conn: Connection, workspace: tuple[UUID, UUID, UUID]
) -> None:
    """The regression guard for the defect this milestone found.

    `ReviewState` is iterated rather than listed, so adding a member that the
    CHECK constraint does not allow fails immediately — which is how the
    `needs_review` / `pending_review` mismatch should have been caught.
    """
    ws, user, doc = workspace

    for ordinal, state in enumerate(ReviewState):
        insert_chunk(
            conn,
            workspace_id=ws,
            document_id=doc,
            ordinal=ordinal,
            text=f"chunk for {state.value}",
            scope="L5",
            owner_user_id=user,
            review_state=state.value,
        )


@requires_db
def test_a_document_can_be_superseded(conn: Connection, workspace: tuple[UUID, UUID, UUID]) -> None:
    """Migration 0010's reason for existing (doc 06 §6).

    Before it, this UPDATE raised `CheckViolation` — and because it shares the
    upload's transaction, it rolled back the *replacement* document too. Uploading
    a new price list would have failed and left the old one authoritative.
    """
    ws, _, doc = workspace

    conn.execute(
        sa.text("UPDATE document SET status = 'superseded' WHERE id = :d AND workspace_id = :ws"),
        {"d": str(doc), "ws": str(ws)},
    )

    status = conn.execute(
        sa.text("SELECT status FROM document WHERE id = :d"), {"d": str(doc)}
    ).scalar_one()
    assert status == "superseded"


@requires_db
def test_a_vector_of_the_wrong_width_is_refused_by_the_column(
    conn: Connection, workspace: tuple[UUID, UUID, UUID]
) -> None:
    """`vector(1024)` is a real constraint, which is why `index_plan` checks the
    width first: this error names a type, not a model."""
    ws, user, doc = workspace

    with pytest.raises(sa.exc.DataError):
        conn.execute(
            sa.text(
                "INSERT INTO chunk"
                " (workspace_id, document_id, ordinal, content, scope, owner_user_id,"
                "  classified_by, confidence, review_state, embedding, embedding_model_id,"
                "  embedding_dim)"
                " VALUES (:ws, :doc, 99, 'too narrow', 'L5', :owner, 'test', 0.0,"
                "         'pending_review', CAST('[0.1,0.2,0.3]' AS vector), 'test', 3)"
            ),
            {"ws": str(ws), "doc": str(doc), "owner": str(user)},
        )


# ── I3: the predicate is part of the ANN query ────────────────


@requires_db
def test_the_scope_predicate_and_the_ann_ordering_are_one_query(
    conn: Connection, workspace: tuple[UUID, UUID, UUID]
) -> None:
    """The shape M6 is built on, proved to execute rather than assumed.

    L2 chunks are company-internal; the L5 chunk belongs to somebody else. A
    Viewer-shaped predicate must return only the L2 rows *and* order them by
    distance in the same statement. Ordering first and filtering after would leak
    through ranking, result counts and latency (migration 0007's own argument).
    """
    ws, user, doc = workspace
    other_user = uuid4()
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(other_user), "e": f"other-{other_user}@example.test"},
    )

    for ordinal, text in enumerate(["annual leave policy", "expense policy", "travel policy"]):
        insert_chunk(
            conn,
            workspace_id=ws,
            document_id=doc,
            ordinal=ordinal,
            text=text,
            scope="L2",
            owner_user_id=None,
            review_state=ReviewState.AUTO_APPROVED.value,
        )
    secret = insert_chunk(
        conn,
        workspace_id=ws,
        document_id=doc,
        ordinal=99,
        text="individual salaries",
        scope="L5",
        owner_user_id=other_user,
    )

    query_vector = DeterministicEmbedder(dim=DIM).embed_query("policy")

    rows = conn.execute(
        sa.text(
            "SELECT id, content, embedding <=> CAST(:q AS vector) AS distance"
            "  FROM chunk"
            " WHERE workspace_id = current_setting('nexus.workspace_id')::uuid"
            "   AND embedding IS NOT NULL"
            "   AND ("
            "         scope IN ('L1','L2')"
            "      OR (scope = 'L5' AND owner_user_id = :uid)"
            "       )"
            " ORDER BY embedding <=> CAST(:q AS vector)"
            " LIMIT 10"
        ),
        {"q": query_vector.to_sql_literal(), "uid": str(user)},
    ).all()

    ids = {UUID(str(r.id)) for r in rows}
    assert len(rows) == 3, "only the L2 rows are reachable"
    assert secret not in ids, "another user's L5 chunk must not appear"
    # Distances are meaningless with a hash embedder; that they exist and are
    # ordered is the property under test, not their values.
    assert [r.distance for r in rows] == sorted(r.distance for r in rows)


@requires_db
def test_a_chunk_with_no_vector_never_appears_in_a_vector_search(
    conn: Connection, workspace: tuple[UUID, UUID, UUID]
) -> None:
    """Why `parsed` matters rather than being cosmetic.

    An unembedded chunk is not findable by any query M6 will write. If the upload
    route called such a document `indexed`, the customer's evidence that their
    price list was searchable would be a status field contradicted by every
    search — with nothing to indicate which was lying.
    """
    ws, _user, doc = workspace

    conn.execute(
        sa.text(
            "INSERT INTO chunk"
            " (workspace_id, document_id, ordinal, content, scope, owner_user_id,"
            "  classified_by, confidence, review_state)"
            " VALUES (:ws, :doc, 0, 'never embedded', 'L2', NULL, 'test', 0.0,"
            "         'auto_approved')"
        ),
        {"ws": str(ws), "doc": str(doc)},
    )

    query_vector = DeterministicEmbedder(dim=DIM).embed_query("anything")
    found = conn.execute(
        sa.text(
            "SELECT count(*) FROM chunk"
            " WHERE embedding IS NOT NULL"
            "   AND embedding <=> CAST(:q AS vector) < 2"
        ),
        {"q": query_vector.to_sql_literal()},
    ).scalar_one()

    assert found == 0, "a NULL embedding is unreachable, so the document is not searchable"
