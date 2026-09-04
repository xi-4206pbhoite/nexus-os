"""Recall at Contributor selectivity, and what `hnsw.iterative_scan` is for.

ADR 0012 is a **measurement**, not a preference: a plain HNSW index with the
permission predicate as an ordinary `WHERE` returns about **5% recall** at the
selectivity of a Contributor reading their own department's rows. Raising
`ef_search` looks like the fix and is not — it rescues a department-sized filter
and leaves narrow ones broken.

The failure mode is the reason this test exists. A retrieval layer with 5%
recall does not error, does not warn, and returns confident, correctly-cited
answers built from a twentieth of the evidence. It is indistinguishable from a
product that is merely not very good, which is how it survives review.

**Synthetic vectors, no model.** Installing `[embeddings]` would pull ~2 GB of
weights into every CI run to test a property that is about the *index and the
predicate*, not about the embedder. What the model would add is whether
`multilingual-e5-large` puts semantically similar text near each other — a real
question, and a different one from this.

**What this does NOT yet do, stated plainly.** `doc/12` P10's acceptance
criterion is that *removing* `SET LOCAL hnsw.iterative_scan` drops recall below
20% and fails. It does not: measured by deleting that line and re-running, this
still passes. At 400 rows Postgres does not need the HNSW index to answer at
all — it can scan the table — so the setting has nothing to change.

Two attempts to make it discriminate, both recorded because the second is the
more interesting failure:

1. The planner was choosing a sequential scan, which is exhaustive — it finds
   every matching row, so the setting had nothing to change. Fixed with
   `SET LOCAL enable_seqscan = off`, which reproduces the *plan* ADR 0012
   measured rather than its row count.
2. It still passes without `iterative_scan`. With the index forced, HNSW at 400
   rows still returns all 20. The graph has no depth at this size: there is no
   long traversal for the filter to exhaust, which is the mechanism the 5%
   comes from.

3. Twenty thousand rows, generated server-side with `generate_series` so the
   insert is two statements rather than twenty thousand round trips. Lifting
   the server `statement_timeout` got past one wall and hit the next: asyncpg's
   own client timeout. Building 20k × 1024-dimension vectors across a link to
   `us-east-1` is minutes of work per run, and the pool is configured — rightly
   — for requests rather than fixtures.

So the corpus is the missing ingredient, and **the environment is why it is
still missing**. This belongs against the local container (`scripts/db-ci.ps1`,
~25 seconds versus Neon's ~5 minutes), where twenty thousand inserts are cheap
and no timeout is in the way. Written down rather than attempted a fourth time
from the wrong machine. Until that exists this asserts recall
**is** high, and would catch a predicate that silently drops the caller's own
rows. It is **not** the `iterative_scan` regression guard, and calling it one
would be the exact failure it was written to prevent: a test that certifies the
thing it was meant to catch.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import _unscoped_session, get_engine, get_sessionmaker
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.retrieval.chunks import search
from app.retrieval.scoped import apply_workspace_scope
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db

DIM = 1024
CORPUS = 400
"""Enough rows for the index to be used at all. Small enough that the fixture is
seconds rather than minutes against a remote database — this measures a ratio,
and the ratio is visible well before the corpus is realistic."""

WANTED = 20
"""How many of the caller's own rows sit near the query. Recall is measured
against these."""


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


def _unit(seed: int, near: bool) -> list[float]:
    """A unit vector. `near=True` clusters tightly around the query direction.

    Deterministic from `seed` so a failure is reproducible — a recall test that
    measures a different corpus each run reports noise as a regression.
    """
    base = [0.0] * DIM
    if near:
        base[0] = 1.0
        base[1 + (seed % 8)] = 0.05
    else:
        base[100 + (seed % 400)] = 1.0
    norm = math.sqrt(sum(v * v for v in base))
    return [v / norm for v in base]


async def _corpus(db: AsyncSession) -> tuple[UUID, UUID, set[UUID]]:
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"recall-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await apply_workspace_scope(db, ws)
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"recall-{ws.hex[:8]}.om"},
    )
    document = uuid4()
    await db.execute(
        sa.text(
            "INSERT INTO document (id, workspace_id, uploaded_by_user_id, filename,"
            " content_type, size_bytes, storage_key, content_sha256, status,"
            " consent_given_at, consent_text_version)"
            " VALUES (:i,:w,:u,'f.pdf','application/pdf',1,:k,:h,'indexed',now(),'v1')"
        ),
        {"i": str(document), "w": str(ws), "u": str(user), "k": f"k/{document}", "h": document.hex},
    )

    wanted: set[UUID] = set()
    for i in range(CORPUS):
        chunk = uuid4()
        # The first WANTED are Finance and near the query — the caller's own
        # rows. Everything else is Sales, which the predicate excludes: that is
        # the selectivity ADR 0012 measured, a needle the filter makes narrow.
        mine = i < WANTED
        if mine:
            wanted.add(chunk)
        await db.execute(
            sa.text(
                "INSERT INTO chunk (id, workspace_id, document_id, ordinal, content, scope,"
                " department, sensitivity, is_dept_aggregate, owner_user_id, review_state,"
                " source_page, source_label, classified_by, confidence, embedding,"
                # `ck_chunk_embedding_provenance` requires these whenever an
                # embedding is present, and it is right to: a vector nobody can
                # say the origin of is a vector nobody can reproduce or
                # re-index when the model changes.
                " embedding_model_id, embedding_dim)"
                " VALUES (:i,:w,:d,:o,:c,'L3',:dept,'normal',false,:u,'auto_approved',"
                "         1,'page 1','rule',1.0, CAST(:v AS vector), 'synthetic-recall', :dim)"
            ),
            {
                "i": str(chunk),
                "w": str(ws),
                "d": str(document),
                "o": i,
                "c": f"chunk {i}",
                "dept": ["finance"] if mine else ["sales"],
                "u": str(user),
                "v": str(_unit(i, near=mine)),
                "dim": DIM,
            },
        )
    await db.commit()
    return user, ws, wanted


@requires_db
async def test_recall_at_contributor_selectivity(app_db: None) -> None:
    """The caller's own rows must actually come back.

    Asserts that a Contributor's own rows come back — which catches a predicate
    that silently drops them. See the module docstring for what this does not
    yet catch, and why the corpus would have to grow to catch it.
    """
    async with _unscoped_session() as db:
        user, ws, wanted = await _corpus(db)
        try:
            await apply_workspace_scope(db, ws)

            # **Force the index.** At 400 rows the planner would rather scan the
            # table, and a sequential scan is exhaustive — it finds every
            # matching row, so `iterative_scan` has nothing to change and the
            # test cannot tell a correct configuration from a broken one.
            #
            # Disabling seqscan is not cheating the measurement: production has
            # far more than 400 rows and will use the index, so this reproduces
            # the *plan* ADR 0012 measured rather than the row count. Growing
            # the corpus to tens of thousands would reach the same plan by
            # spending minutes of insert time per run.
            await db.execute(sa.text("SET LOCAL enable_seqscan = off"))

            scope = ScopedSession(
                user_id=user,
                tenant_id=uuid4(),
                workspace_id=ws,
                role=Role.CONTRIBUTOR,
                departments=frozenset({Department.FINANCE}),
            )

            found = {
                p.id for p in await search(db, scope, embedding=_unit(0, near=True), limit=WANTED)
            }
            recall = len(found & wanted) / len(wanted)

            assert recall >= 0.8, (
                f"recall {recall:.0%} at Contributor selectivity. ADR 0012 measured ~5% "
                "without `SET LOCAL hnsw.iterative_scan` — and 5% recall does not error "
                "or warn, it returns confident correctly-cited answers built from a "
                "twentieth of the evidence."
            )

            # Nothing outside the department leaked in while chasing recall.
            # A retrieval layer can always reach 100% recall by returning
            # everything, so the number is only meaningful beside this.
            assert found <= wanted, "the predicate must hold even when the index works hard"
        finally:
            await apply_workspace_scope(db, ws)
            for statement in (
                "DELETE FROM chunk WHERE workspace_id = :w",
                "DELETE FROM document WHERE workspace_id = :w",
                "DELETE FROM workspace WHERE id = :w",
            ):
                await db.execute(sa.text(statement), {"w": str(ws)})
            await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            await db.commit()
