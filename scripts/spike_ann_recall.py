"""Task 5.7 — filtered-ANN recall at expected cardinality.

**The question M6 cannot be designed without.** The retrieval layer must apply
the permission predicate *inside* the vector query (I3), not after it. Two ways
to do that in pgvector:

1. **One HNSW index plus a WHERE clause.** Simple, one index. But an HNSW search
   walks a graph built over *all* rows; a selective filter can leave the walk
   returning far fewer than `k` matching rows, or missing the true nearest ones
   entirely. pgvector 0.8 added `hnsw.iterative_scan` to keep searching until it
   has enough — this spike measures whether that actually recovers recall.
2. **Partial indexes per scope.** Each index covers one scope, so every row it
   contains already satisfies the filter. Better recall by construction, but the
   number of indexes multiplies with scopes × departments, and a chunk whose
   scope changes after review has to move between them.

If (1) holds up, M6 is a single index and an ordinary predicate. If it does not,
M6 needs a partial-index strategy and a plan for re-indexing on review — a
materially different design.

**What this measures, and what it does not.** Recall is computed against exact
search on the same data, so the numbers are real for this distribution. The
vectors are synthetic: uniformly random on the unit sphere. Real embeddings
cluster, and clustering generally *helps* HNSW, so treat these figures as a
conservative floor rather than a prediction. What transfers exactly is the
*mechanism* — whether the iterative scan finds matching rows behind a selective
filter at all.

Run:  .\\scripts\\api.ps1 is not needed; this talks to the database directly.
      cd services\\api; .\\.venv\\Scripts\\python.exe ..\\..\\scripts\\spike_ann_recall.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import sqlalchemy as sa  # noqa: E402

from tests.dburl import database_url  # noqa: E402

DIM = 1024
ROWS = 20_000
"""Enough for the graph to matter. A few thousand rows are searched almost
exactly by any method, which would make the comparison meaningless."""

K = 10
PROBE_QUERIES = 12
"""Every query is a round trip to us-east-2. Twelve is enough to separate
90% recall from 40%, which is the size of difference this decision turns on."""

# Selectivities worth testing, expressed as the fraction of rows a caller may
# reach. The interesting end is the narrow one: a Contributor restricted to
# their own L5 rows may match well under 1% of the table, and that is precisely
# where an unfiltered graph walk has the least to work with.
SELECTIVITIES = [
    ("L2 company-wide", 0.60),
    ("L3 one department", 0.15),
    ("L5 own rows only", 0.02),
    ("L5, very narrow", 0.005),
]


def unit_vector(rng: random.Random) -> list[float]:
    v = [rng.gauss(0, 1) for _ in range(DIM)]
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


def literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def main() -> int:
    url = database_url()
    if url is None:
        print("No database configured. Set NEXUS_DATABASE_URL or fill .env.")
        return 1

    rng = random.Random(20260818)
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)

    with engine.connect() as conn:
        print(f"pgvector: {_extension_version(conn)}")
        print(f"building {ROWS:,} rows x {DIM}d ...")

        _build(conn, rng)
        conn.commit()

        print("\nbuilding HNSW index (m=16, ef_construction=64) ...")
        started = time.monotonic()
        conn.execute(
            sa.text(
                "CREATE INDEX spike_hnsw ON ann_spike"
                " USING hnsw (embedding vector_cosine_ops)"
                " WITH (m = 16, ef_construction = 64)"
            )
        )
        conn.commit()
        print(f"  built in {time.monotonic() - started:.1f}s")

        queries = [unit_vector(rng) for _ in range(PROBE_QUERIES)]

        print(f"\nrecall@{K} against exact search, over {PROBE_QUERIES} queries")
        print(f"{'filter':<22} {'rows':>8} {'plain':>9} {'iterative':>11} {'partial':>9}")
        print("-" * 64)

        for label, selectivity in SELECTIVITIES:
            matching = int(ROWS * selectivity)
            # Once per (query, selectivity), not once per method.
            truth = [_exact_seqscan(conn, q, selectivity) for q in queries]
            plain = _recall(conn, queries, truth, selectivity, iterative=None)
            iterative = _recall(conn, queries, truth, selectivity, iterative="relaxed_order")
            partial = _recall_partial(conn, queries, truth, selectivity)
            print(
                f"{label:<22} {matching:>8,} {plain:>8.1%} {iterative:>10.1%} {partial:>8.1%}"
            )

        _teardown(conn)
        conn.commit()

    print("\nInterpretation")
    print("  plain      — one HNSW index, ordinary WHERE. What M6 would do by default.")
    print("  iterative  — same index with hnsw.iterative_scan = relaxed_order.")
    print("  partial    — an index covering only the matching rows. The upper bound.")
    print("\nVectors are uniformly random; real embeddings cluster, which helps HNSW.")
    print("Read these as a conservative floor for the mechanism, not a forecast.")
    return 0


def _extension_version(conn: sa.Connection) -> str:
    row = conn.execute(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    return str(row or "not installed")


def _build(conn: sa.Connection, rng: random.Random) -> None:
    conn.execute(sa.text("DROP TABLE IF EXISTS ann_spike"))
    conn.execute(
        sa.text(
            "CREATE TABLE ann_spike ("
            "  id bigserial PRIMARY KEY,"
            f" embedding vector({DIM}) NOT NULL,"
            "  bucket double precision NOT NULL"
            ")"
        )
    )

    batch: list[dict[str, object]] = []
    for _ in range(ROWS):
        batch.append({"e": literal(unit_vector(rng)), "b": rng.random()})
        if len(batch) == 500:
            _flush(conn, batch)
            batch.clear()
    if batch:
        _flush(conn, batch)


def _flush(conn: sa.Connection, batch: list[dict[str, object]]) -> None:
    conn.execute(
        sa.text("INSERT INTO ann_spike (embedding, bucket) VALUES (CAST(:e AS vector), :b)"),
        batch,
    )


def _exact(conn: sa.Connection, query: list[float], selectivity: float) -> set[int]:
    rows = conn.execute(
        sa.text(
            "SELECT id FROM ann_spike WHERE bucket < :sel"
            " ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"sel": selectivity, "q": literal(query), "k": K},
    ).scalars()
    return set(rows)


def _recall(
    conn: sa.Connection,
    queries: list[list[float]],
    truth: list[set[int]],
    selectivity: float,
    *,
    iterative: str | None,
) -> float:
    conn.execute(sa.text(f"SET LOCAL hnsw.iterative_scan = {iterative or 'off'}"))

    total = 0.0
    for query, expected in zip(queries, truth, strict=True):
        found = _exact(conn, query, selectivity)
        total += len(found & expected) / max(1, len(expected))
    return total / len(queries)


def _exact_seqscan(conn: sa.Connection, query: list[float], selectivity: float) -> set[int]:
    """Ground truth: the index is disabled, so this is a full scan."""
    conn.execute(sa.text("SET LOCAL enable_indexscan = off"))
    conn.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
    truth = _exact(conn, query, selectivity)
    conn.execute(sa.text("SET LOCAL enable_indexscan = on"))
    conn.execute(sa.text("SET LOCAL enable_bitmapscan = on"))
    return truth


def _recall_partial(
    conn: sa.Connection,
    queries: list[list[float]],
    truth: list[set[int]],
    selectivity: float,
) -> float:
    """The upper bound: an index containing only rows the filter admits."""
    conn.execute(sa.text("DROP INDEX IF EXISTS spike_partial"))
    conn.execute(
        sa.text(
            "CREATE INDEX spike_partial ON ann_spike"
            " USING hnsw (embedding vector_cosine_ops)"
            " WITH (m = 16, ef_construction = 64)"
            f" WHERE bucket < {selectivity}"
        )
    )
    conn.commit()
    value = _recall(conn, queries, truth, selectivity, iterative=None)
    conn.execute(sa.text("DROP INDEX IF EXISTS spike_partial"))
    conn.commit()
    return value


def _teardown(conn: sa.Connection) -> None:
    conn.execute(sa.text("DROP TABLE IF EXISTS ann_spike"))


if __name__ == "__main__":
    raise SystemExit(main())
