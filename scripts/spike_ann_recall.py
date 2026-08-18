"""Task 5.7 - filtered-ANN recall at expected cardinality.

**The question M6 cannot be designed without.** The retrieval layer must apply
the permission predicate *inside* the vector query (I3), not after it. Two ways
to do that in pgvector:

1. **One HNSW index plus a WHERE clause.** Simple, one index. But an HNSW search
   walks a graph built over *all* rows; a selective filter can leave the walk
   returning far fewer than `k` matching rows, or missing the true nearest ones
   entirely. pgvector 0.8 added `hnsw.iterative_scan` to keep searching until it
   has enough - this spike measures whether that actually recovers recall.
2. **Partial indexes per scope.** Each index covers one scope, so every row it
   contains already satisfies the filter. Better recall by construction, but the
   number of indexes multiplies with scopes x departments, and a chunk whose
   scope changes after review has to move between them.

If (1) holds up, M6 is a single index and an ordinary predicate. If it does not,
M6 needs a partial-index strategy and a plan for re-indexing on review - a
materially different design.

**This is the second version. The first produced a table that looked like an
answer and was not one**, and the three defects are worth stating because each
would have been invisible in the output:

- *The vectors were isotropic.* Uniformly random unit vectors in 1024d have
  intrinsic dimension ~1023 - they lie near no lower-dimensional manifold, which
  is the worst possible case for a graph index and unlike any real embedding.
  Measured locally: 0% of a query's top-10 shared its topic. All three
  strategies were floored equally, landing within 5 points of each other, so the
  comparison could not discriminate. Vectors here are 40 topic centroids plus
  noise at sd=0.05, which puts 100% of each top-10 in the query's own topic.
- *Two of the four rows were not ANN searches at all.* Below roughly 60%
  selectivity the planner abandoned the index and scanned exactly, so those
  cells compared exact search against exact search and reported 100% recall.
  This version forces index use for the recall measurement and reports the
  planner's unforced choice separately - because "the planner prefers an exact
  scan here" is a genuine finding about small workspaces, not a number to hide.
- *`hnsw.ef_search` was never recorded*, though it sets how many candidates any
  of these searches explores and is the first knob to reach for when filtered
  recall disappoints. Both the default and a raised value are measured.

**What this measures, and what it does not.** Recall is computed against exact
search on the same data, so the numbers are real for this distribution. The
`bucket` column stands in for the permission predicate and is drawn
independently of topic - the realistic case, since who may read a chunk has
little to do with what it is about. Correlated permissions would be a separate
run.

Run:  cd services\\api; .\\.venv\\Scripts\\python.exe ..\\..\\scripts\\spike_ann_recall.py
"""

from __future__ import annotations

import os
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import sqlalchemy as sa  # noqa: E402

from tests.dburl import database_url  # noqa: E402

DIM = 1024
ROWS = 20_000
"""Enough for the graph to matter. A few thousand rows are searched almost
exactly by any method, which would make the comparison meaningless."""

CLUSTERS = 40
NOISE_SD = 0.05
"""Chosen by measurement, not taste. At sd=0.35 only 4% of a query's top-10
shared its topic - chance is 2.5% with 40 topics, i.e. noise. At 0.05 it is
100%, which is what "this row is a real neighbour" has to mean before recall
says anything about a graph walk."""

K = 10
PROBE_QUERIES = 10
"""Every query is a round trip to us-east-2. Ten is enough to separate 90%
recall from 40%, which is the size of difference this decision turns on."""

EF_SEARCH = (40, 100)
"""40 is the pgvector default - what M6 would get without thinking about it.
100 is the cheapest available remedy if the default disappoints."""

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

TABLE = f"ann_spike_{os.getpid()}"
INDEX = f"{TABLE}_hnsw"
PARTIAL = f"{TABLE}_partial"
"""Namespaced per process, and not decoration.

A concurrent run of an earlier version of this spike was found holding a
20,000-row `ann_spike` of its own shape, creating and dropping indexes on it.
Two runs sharing one table name means ground truth and measurement can be
taken against different contents, which yields a recall table that looks
plausible and means nothing. One shared database, several sessions.
"""

ANN_SQL = (
    f"SELECT id FROM {TABLE} WHERE bucket < :sel"
    " ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
)


def unit(v: list[float]) -> list[float]:
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
    centroids = [unit([rng.gauss(0, 1) for _ in range(DIM)]) for _ in range(CLUSTERS)]

    def topical(centroid: list[float]) -> list[float]:
        return unit([x + rng.gauss(0, NOISE_SD) for x in centroid])

    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)

    with engine.connect() as conn:
        print(f"pgvector {_extension_version(conn)}")
        print(
            f"{ROWS:,} rows x {DIM}d | {CLUSTERS} topics, noise sd={NOISE_SD}"
            f" | k={K}, {PROBE_QUERIES} queries"
        )
        print(f"\nbuilding {ROWS:,} rows ...")
        _build(conn, rng, centroids, topical)

        print("building HNSW index (m=16, ef_construction=64) ...")
        started = time.monotonic()
        conn.execute(
            sa.text(
                f"CREATE INDEX {INDEX} ON {TABLE}"
                " USING hnsw (embedding vector_cosine_ops)"
                " WITH (m = 16, ef_construction = 64)"
            )
        )
        conn.commit()
        conn.execute(sa.text(f"ANALYZE {TABLE}"))
        conn.commit()
        print(f"  built in {time.monotonic() - started:.1f}s")

        # A real query is a question about something, so probes are topical too.
        queries = [topical(centroids[rng.randrange(CLUSTERS)]) for _ in range(PROBE_QUERIES)]

        header = f"\nrecall@{K} vs exact search, index use forced (enable_seqscan = off)"
        print(header)
        cols = "".join(f"{'ef=' + str(ef):>26}" for ef in EF_SEARCH)
        print(f"{'filter':<20}{'rows':>8}{cols}")
        sub = "".join(f"{'plain':>8}{'iter':>9}{'partial':>9}" for _ in EF_SEARCH)
        print(f"{'':<20}{'':>8}" + sub)
        print("-" * (28 + 26 * len(EF_SEARCH)))

        natural: list[tuple[str, int, str]] = []

        for label, selectivity in SELECTIVITIES:
            matching = int(ROWS * selectivity)
            truth = [_exact_truth(conn, q, selectivity) for q in queries]

            # What the planner does when left alone. Recorded once per
            # selectivity, before any forcing, and reported separately: an
            # exact scan is a legitimate outcome, not a recall figure.
            natural.append((label, matching, _plan_choice(conn, queries[0], selectivity)))

            # Two phases, and the order is load-bearing. The partial index must
            # not exist while `plain` and `iter` are measured: the planner would
            # be free to choose it, and both columns would quietly become a
            # second partial measurement showing suspiciously good recall.
            plain: dict[int, float] = {}
            iterative: dict[int, float] = {}
            for ef in EF_SEARCH:
                plain[ef] = _recall(conn, queries, truth, selectivity, ef=ef, iterative=None)
                iterative[ef] = _recall(
                    conn, queries, truth, selectivity, ef=ef, iterative="relaxed_order"
                )

            # Built once per selectivity rather than once per (selectivity, ef).
            partial: dict[int, float] = {}
            _create_partial(conn, selectivity)
            try:
                for ef in EF_SEARCH:
                    partial[ef] = _recall(
                        conn, queries, truth, selectivity, ef=ef, iterative=None
                    )
            finally:
                _drop_partial(conn)

            cells = [
                f"{plain[ef]:>7.1%}{iterative[ef]:>9.1%}{partial[ef]:>9.1%}"
                for ef in EF_SEARCH
            ]
            print(f"{label:<20}{matching:>8,}" + "".join(f"{c:>26}" for c in cells))

        print("\nplanner's own choice, unforced:")
        for label, matching, choice in natural:
            print(f"  {label:<20}{matching:>8,}  ->  {choice}")

        _teardown(conn)
        conn.commit()

    print("\nReading this")
    print("  plain    - one HNSW index, ordinary WHERE. What M6 would do by default.")
    print("  iter     - the same index with hnsw.iterative_scan = relaxed_order.")
    print("  partial  - an index covering only the matching rows. The upper bound.")
    print("\nRecall is measured with the index forced, so every cell is an ANN result.")
    print("Where the planner picks a seq scan it returns exact answers instead, which")
    print("is why the unforced choice is reported rather than folded into the table.")
    return 0


def _extension_version(conn: sa.Connection) -> str:
    row = conn.execute(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    return str(row or "not installed")


def _build(
    conn: sa.Connection,
    rng: random.Random,
    centroids: list[list[float]],
    topical: Callable[[list[float]], list[float]],
) -> None:
    conn.execute(sa.text(f"DROP TABLE IF EXISTS {TABLE}"))
    conn.execute(
        sa.text(
            f"CREATE TABLE {TABLE} ("
            "  id bigserial PRIMARY KEY,"
            f" embedding vector({DIM}) NOT NULL,"
            "  topic int NOT NULL,"
            # Stands in for the permission predicate. Independent of topic:
            # who may read a chunk has little to do with what it is about.
            "  bucket double precision NOT NULL"
            ")"
        )
    )
    conn.commit()

    # Committing per batch. A single long transaction pushing 20k x 1024 floats
    # to us-east-2 was dropped mid-insert by the serverless host once already.
    written = 0
    while written < ROWS:
        size = min(200, ROWS - written)
        batch: list[dict[str, object]] = []
        for _ in range(size):
            topic = rng.randrange(CLUSTERS)
            batch.append(
                {
                    "e": literal(topical(centroids[topic])),
                    "t": topic,
                    "b": rng.random(),
                }
            )
        conn.execute(
            sa.text(
                f"INSERT INTO {TABLE} (embedding, topic, bucket)"
                " VALUES (CAST(:e AS vector), :t, :b)"
            ),
            batch,
        )
        conn.commit()
        written += size


def _ann(conn: sa.Connection, query: list[float], selectivity: float) -> set[int]:
    rows = conn.execute(
        sa.text(ANN_SQL), {"sel": selectivity, "q": literal(query), "k": K}
    ).scalars()
    return set(rows)


def _exact_truth(conn: sa.Connection, query: list[float], selectivity: float) -> set[int]:
    """Ground truth: every index path off, so this is a full scan."""
    conn.execute(sa.text("SET LOCAL enable_indexscan = off"))
    conn.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
    truth = _ann(conn, query, selectivity)
    conn.commit()  # clears the SET LOCALs rather than trusting a reset
    return truth


def _plan_choice(conn: sa.Connection, query: list[float], selectivity: float) -> str:
    plan = "\n".join(
        str(r[0])
        for r in conn.execute(
            sa.text("EXPLAIN " + ANN_SQL),
            {"sel": selectivity, "q": literal(query), "k": K},
        )
    )
    if PARTIAL in plan:
        return "partial HNSW"
    if INDEX in plan:
        return "plain HNSW"
    if "Seq Scan" in plan:
        return "SEQ SCAN (exact answers)"
    return "unrecognised plan"


def _recall(
    conn: sa.Connection,
    queries: list[list[float]],
    truth: list[set[int]],
    selectivity: float,
    *,
    ef: int,
    iterative: str | None,
) -> float:
    conn.execute(sa.text(f"SET LOCAL hnsw.ef_search = {ef}"))
    conn.execute(sa.text(f"SET LOCAL hnsw.iterative_scan = {iterative or 'off'}"))
    # Force the graph walk. Without this the planner switches to an exact scan
    # at narrow selectivities and the cell silently reports 100%.
    conn.execute(sa.text("SET LOCAL enable_seqscan = off"))

    total = 0.0
    for query, expected in zip(queries, truth, strict=True):
        found = _ann(conn, query, selectivity)
        total += len(found & expected) / max(1, len(expected))
    conn.commit()
    return total / len(queries)


def _create_partial(conn: sa.Connection, selectivity: float) -> None:
    """The upper bound: an index containing only the rows the filter admits.

    A partial index that scores below ~100% is a sign the harness is measuring
    something other than what it claims, not a finding about pgvector.
    """
    conn.execute(sa.text(f"DROP INDEX IF EXISTS {PARTIAL}"))
    conn.execute(
        sa.text(
            f"CREATE INDEX {PARTIAL} ON {TABLE}"
            " USING hnsw (embedding vector_cosine_ops)"
            " WITH (m = 16, ef_construction = 64)"
            f" WHERE bucket < {selectivity}"
        )
    )
    conn.commit()


def _drop_partial(conn: sa.Connection) -> None:
    conn.execute(sa.text(f"DROP INDEX IF EXISTS {PARTIAL}"))
    conn.commit()


def _teardown(conn: sa.Connection) -> None:
    conn.execute(sa.text(f"DROP INDEX IF EXISTS {PARTIAL}"))
    conn.execute(sa.text(f"DROP TABLE IF EXISTS {TABLE}"))


if __name__ == "__main__":
    raise SystemExit(main())
