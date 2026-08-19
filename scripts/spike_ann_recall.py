"""Task 5.7 — filtered-ANN recall at expected cardinality.

**The question M6 cannot be designed without.** The retrieval layer must apply the
permission predicate *inside* the vector query (I3), not after it. Two ways to do
that in pgvector:

1. **One HNSW index plus a WHERE clause.** Simple, one index. But an HNSW search
   walks a graph built over *all* rows; a selective filter can leave the walk
   returning far fewer than `k` matching rows, or missing the true nearest ones.
   pgvector 0.8 added `hnsw.iterative_scan` to keep searching until it has enough —
   this spike measures whether that actually recovers recall.
2. **Partial indexes per scope.** Each index covers rows that already satisfy one
   filter, so recall is good by construction. But the index count multiplies with
   scopes x departments, and a chunk whose scope changes at review has to move
   between them — on a table where review is routine (I4 sends every
   unclassifiable chunk through it).

If (1) holds up, M6 is a single index and an ordinary predicate. If it does not, M6
needs a partial-index strategy and a plan for re-indexing on review — a materially
different design.

**The predicate is the real one.** M6's predicate is a four-branch disjunction over
`scope`, `department[]` and `owner_user_id` (`ARCHITECTURE.md` §3.3). A disjunction
cannot become an index condition — it can only be a filter applied to rows the
graph walk already returned, which is the mechanism under test. So the profiles are
the role → scope rows of doc 06 §2.3.

---

## Two corrections the first run forced

The first version of this script produced numbers that contradicted themselves: an
Owner matching 90% of rows scored 9.2% recall, and the narrowest profile scored
100% on `plain` while scoring 64% on `partial` — which is defined as the upper
bound and cannot be lower. Both were measurement defects, and both are the kind
that produce a *confident* wrong answer, so they are worth recording here.

**Vectors must cluster.** 1024 independent gaussians are all near-orthogonal:
measured on this database, mean cosine distance 0.9977 with the nearest of 300 rows
only 3 sd below the mean. The true top-10 is therefore arbitrary among thousands of
near-ties, so recall@10 measures tie-breaking rather than index quality — and gets
*worse* as more rows match, which is exactly the inverted pattern the first run
showed. Rows here are now drawn around `TOPICS` centroids, giving the
neighbourhood structure real embeddings have and recall something to be right about.

**The chosen plan must be recorded, never assumed.** At 10% selectivity Postgres
abandoned the HNSW index for a sequential scan, which is *exact* — so it scored
100% recall while measuring nothing about the index. A seq-scan fallback reading as
perfect recall is the single most misleading output this spike could produce, so
every figure below now carries the scan type taken from `EXPLAIN`. `hnsw` means the
number describes the index; `seq` means Postgres judged the filter selective enough
to search exactly, and recall is trivially 1.0.

That second point is not only a fix — it is half the answer. The planner declining
the index at high selectivity is correct behaviour and a useful property for M6.

**What this still does not measure.** Synthetic clusters are more separable than
real embeddings, so `hnsw` recall here is optimistic, where the first run's was
meaninglessly pessimistic. What transfers is the *comparison* between plain,
iterative and partial at equal selectivity, and which plan the optimiser picks.

Run (PowerShell, from the repo root):
    cd services\\api; .\\.venv\\Scripts\\python.exe ..\\..\\scripts\\spike_ann_recall.py

Takes roughly 15 minutes against Neon: every ground-truth query is a full scan of
80 MB, an ocean away.
"""

# ruff: noqa: S608
# Predicates are spliced rather than bound throughout, and deliberately: a partial
# index can only be matched to a query whose predicate the planner can *prove*
# implies the index predicate, which it cannot do through a parameter it has not
# seen. Every spliced value here is a module constant or a uuid this script itself
# generated - there is no external input to this file.

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import sqlalchemy as sa

from tests.dburl import database_url

DIM = 1024
ROWS = 20_000
"""Enough for the graph to matter. A few thousand rows are searched almost exactly
by any method, which would make the comparison meaningless."""

TOPICS = 250
"""Cluster count. 20,000 rows over 250 topics is 80 rows per neighbourhood — the
same order as a real workspace, where a query about pricing should find the handful
of chunks about pricing rather than a tenth of the corpus."""

SPREAD = 0.45
"""Within-cluster noise relative to the centroid. Low enough that neighbourhoods
exist, high enough that clusters overlap and the search is not trivial."""

K = 10
PROBE_QUERIES = 8
"""Each probe costs one full scan for ground truth. Eight separates 90% recall from
40%, which is the size of difference this decision turns on."""

DEPARTMENTS = ("marketing", "sales", "finance", "operations", "hr", "strategy")

SEED = 0.20260818
"""`setseed` makes the corpus reproducible, so a rerun after a pgvector upgrade
compares like with like."""


@dataclass(frozen=True)
class Profile:
    """A caller, expressed as the predicate their scope set produces.

    `sql` is spliced rather than bound: a partial index can only be matched to a
    query whose predicate the planner can *prove* implies the index predicate,
    which it cannot do through a parameter it has not seen.
    """

    label: str
    sql: str


PROFILES = (
    Profile("Owner (all depts)", "scope IN ('L1','L2') OR scope = 'L3'"),
    Profile(
        "Dept Manager (1 of 6)",
        "scope IN ('L1','L2') OR (scope = 'L3' AND department && ARRAY['finance'])",
    ),
    Profile(
        "Contributor (restricted)",
        "scope IN ('L1','L2')"
        " OR (scope = 'L3' AND department && ARRAY['finance'] AND NOT is_dept_aggregate)",
    ),
    Profile("Viewer (L1+L2)", "scope IN ('L1','L2')"),
    # The narrowest real case, and where every chunk sits today.
    Profile("Own L5 only", "scope = 'L5' AND owner_user_id = :uid"),
)

HNSW_OPTS = "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"


@dataclass
class Measurement:
    recall: float
    scan: str
    """`hnsw`, `seq`, or whatever EXPLAIN reported. The number means nothing
    without it."""


def main() -> int:
    url = database_url()
    if url is None:
        _say("No database configured. Set NEXUS_DATABASE_URL or fill .env.")
        return 1

    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)

    with engine.connect() as conn:
        _say(f"pgvector {_extension_version(conn)} · postgres {_server_version(conn)}")
        if not _has_random_normal(conn):
            _say("random_normal() needs PostgreSQL 16+. Cannot generate rows.")
            return 1

        _say(f"generating {ROWS:,} rows x {DIM}d in {TOPICS} clusters, server-side ...")
        started = time.monotonic()
        owner = _build(conn)
        conn.commit()
        _say(f"  generated in {time.monotonic() - started:.1f}s")

        if not _corpus_is_sane(conn):
            _teardown(conn)
            conn.commit()
            return 1

        queries = _query_vectors(conn)

        _say(f"building HNSW index {HNSW_OPTS.split('WITH')[1].strip()} ...")
        started = time.monotonic()
        _create_index(conn, "spike_hnsw", where=None)
        _say(f"  built in {time.monotonic() - started:.1f}s")

        # Phase 1 — one full index, every profile. No rebuilds.
        truths: dict[str, list[set[int]]] = {}
        plain: dict[str, Measurement] = {}
        iterative: dict[str, Measurement] = {}
        rows_matching: dict[str, int] = {}

        for profile in PROFILES:
            rows_matching[profile.label] = _matching_rows(conn, profile, owner)
            truths[profile.label] = _ground_truth(conn, queries, profile, owner)
            plain[profile.label] = _measure(
                conn, queries, truths[profile.label], profile, owner, iterative="off"
            )
            iterative[profile.label] = _measure(
                conn, queries, truths[profile.label], profile, owner, iterative="relaxed_order"
            )

        # Phase 2 — the full index is dropped once, then one partial index per
        # profile. Leaving the full index in place would let the planner pick it
        # and quietly report `plain` a second time.
        conn.commit()
        conn.execute(sa.text("DROP INDEX IF EXISTS spike_hnsw"))
        conn.commit()

        partial: dict[str, Measurement] = {}
        for profile in PROFILES:
            _create_index(conn, "spike_partial", where=_predicate(profile, owner))
            partial[profile.label] = _measure(
                conn, queries, truths[profile.label], profile, owner, iterative="off"
            )
            conn.commit()
            conn.execute(sa.text("DROP INDEX IF EXISTS spike_partial"))
            conn.commit()

        _report(rows_matching, plain, iterative, partial)

        _teardown(conn)
        conn.commit()

    return 0


def _report(
    rows_matching: dict[str, int],
    plain: dict[str, Measurement],
    iterative: dict[str, Measurement],
    partial: dict[str, Measurement],
) -> None:
    _say("")
    _say(f"recall@{K} against exact search, over {PROBE_QUERIES} queries")
    _say("`seq` = the planner searched exactly; recall is 1.0 by construction")
    _say("")
    header = (
        f"{'caller profile':<26} {'rows':>7} {'sel':>6}"
        f" {'plain':>14} {'iterative':>14} {'partial':>14}"
    )
    _say(header)
    _say("-" * len(header))
    for profile in PROFILES:
        label = profile.label
        _say(
            f"{label:<26} {rows_matching[label]:>7,} {rows_matching[label] / ROWS:>5.1%}"
            f" {_cell(plain[label]):>14} {_cell(iterative[label]):>14}"
            f" {_cell(partial[label]):>14}"
        )
    _say("")
    _say("  plain      one HNSW index, ordinary WHERE. What M6 would do by default.")
    _say("  iterative  same index, hnsw.iterative_scan = relaxed_order.")
    _say("  partial    an index covering only the matching rows. The upper bound.")
    _say("")
    _say(f"Synthetic clusters ({TOPICS} topics, spread {SPREAD}) separate more cleanly than")
    _say("real embeddings, so hnsw recall here is optimistic. The comparison between")
    _say("columns at equal selectivity is what transfers, along with the plan chosen.")


def _cell(m: Measurement) -> str:
    return f"{m.recall:.1%} {m.scan}"


# ── Building the corpus ───────────────────────────────────────


def _vector_expr(scale: str = "") -> str:
    """SQL producing one random vector. `scale` multiplies each component."""
    component = f"(random_normal(){scale})::text"
    return f"('[' || string_agg({component}, ',') || ']')::vector"


def _build(conn: sa.Connection) -> str:
    """Create and populate the spike table. Returns the owner uuid used for L5.

    Scope mix is roughly what a real workspace produces once a classifier exists: a
    little company-public, a lot internal, most department-level, and a tail of
    withheld personal content.

    Every row is `centroid + noise`, so the corpus has neighbourhoods. pgvector
    supports vector addition, and the noise is scaled at generation time because it
    has no scalar multiply.
    """
    conn.execute(sa.text("DROP TABLE IF EXISTS ann_spike"))
    conn.execute(sa.text("DROP TABLE IF EXISTS spike_centroid"))
    conn.execute(
        sa.text(
            "CREATE TABLE ann_spike ("
            "  id bigserial PRIMARY KEY,"
            f" embedding vector({DIM}) NOT NULL,"
            "  scope text NOT NULL,"
            "  department text[] NOT NULL DEFAULT '{}',"
            "  owner_user_id uuid,"
            "  is_dept_aggregate boolean NOT NULL DEFAULT false"
            ")"
        )
    )
    conn.execute(
        sa.text(f"CREATE TABLE spike_centroid (t int PRIMARY KEY, vec vector({DIM}) NOT NULL)")
    )

    owner = str(conn.execute(sa.text("SELECT gen_random_uuid()")).scalar_one())
    conn.execute(sa.text("SELECT setseed(:seed)"), {"seed": SEED})

    # The lateral subqueries reference g.i so they are correlated and cannot be
    # hoisted; `random_normal()` being volatile is not on its own a guarantee the
    # planner re-evaluates it per row. `_corpus_is_sane` verifies the outcome.
    conn.execute(
        sa.text(
            f"""
            INSERT INTO spike_centroid (t, vec)
            SELECT g.i, v.vec
            FROM generate_series(1, :topics) AS g(i)
            CROSS JOIN LATERAL (
                SELECT {_vector_expr()} AS vec
                FROM generate_series(1, {DIM}) AS d(j) WHERE d.j + g.i > 0
            ) v
            """
        ),
        {"topics": TOPICS},
    )

    conn.execute(
        sa.text(
            f"""
            INSERT INTO ann_spike (embedding, scope, department, owner_user_id,
                                   is_dept_aggregate)
            SELECT
                c.vec + n.vec,
                s.scope,
                CASE WHEN s.scope = 'L3'
                     THEN ARRAY[(ARRAY{list(DEPARTMENTS)!r})[1 + (g.i % {len(DEPARTMENTS)})]]
                     ELSE '{{}}'::text[]
                END,
                CASE WHEN s.scope = 'L5' THEN CAST(:owner AS uuid) ELSE NULL END,
                (g.i % 20 = 0)
            FROM generate_series(1, :rows) AS g(i)
            JOIN spike_centroid c ON c.t = 1 + (g.i % :topics)
            CROSS JOIN LATERAL (
                SELECT {_vector_expr(f" * {SPREAD}")} AS vec
                FROM generate_series(1, {DIM}) AS d(j) WHERE d.j + g.i > 0
            ) n
            CROSS JOIN LATERAL (
                SELECT CASE
                    WHEN g.i % 20 = 1 THEN 'L1'
                    WHEN g.i % 20 < 7 THEN 'L2'
                    WHEN g.i % 20 < 18 THEN 'L3'
                    ELSE 'L5'
                END AS scope
            ) s
            """
        ),
        {"rows": ROWS, "owner": owner, "topics": TOPICS},
    )
    return owner


def _corpus_is_sane(conn: sa.Connection) -> bool:
    """Prove the corpus has distinct vectors *and* real neighbourhoods.

    Both are failure modes that produce plausible numbers rather than errors: one
    vector repeated 20,000 times, or 20,000 mutually orthogonal ones. The first
    run of this spike shipped with the second and its numbers contradicted
    themselves.
    """
    distinct = conn.execute(sa.text("SELECT count(DISTINCT embedding) FROM ann_spike")).scalar()
    if distinct is None or distinct < ROWS * 0.99:
        _say(f"  ABORT: only {distinct} distinct vectors in {ROWS} rows.")
        return False
    _say(f"  {distinct:,} distinct vectors")

    row = conn.execute(
        sa.text(
            """
            WITH q AS (SELECT embedding AS v FROM ann_spike ORDER BY id LIMIT 1),
                 f AS (SELECT id FROM ann_spike ORDER BY id LIMIT 1),
                 d AS (SELECT a.embedding <=> q.v AS dist
                       FROM ann_spike a, q WHERE a.id <> (SELECT id FROM f))
            SELECT min(dist) AS nearest, avg(dist) AS mean, stddev(dist) AS sd FROM d
            """
        )
    ).one()
    separation = (float(row.mean) - float(row.nearest)) / max(float(row.sd), 1e-9)
    _say(
        f"  nearest {float(row.nearest):.4f} · mean {float(row.mean):.4f}"
        f" · {separation:.1f} sd of separation"
    )
    if separation < 5.0:
        # Below this the top-k is a set of near-ties and recall@k measures
        # tie-breaking, not the index. That is what invalidated the first run.
        _say(
            f"  ABORT: {separation:.1f} sd is too little structure for recall@{K} to mean anything."
        )
        return False
    return True


# ── Measurement ───────────────────────────────────────────────


def _query_vectors(conn: sa.Connection) -> list[str]:
    """Probes drawn near a centroid, so each has a real neighbourhood to find."""
    rows = conn.execute(
        sa.text(
            f"""
            SELECT (c.vec + n.vec)::text AS vec
            FROM generate_series(1, :n) AS g(i)
            JOIN spike_centroid c ON c.t = 1 + (g.i * 7 % :topics)
            CROSS JOIN LATERAL (
                SELECT {_vector_expr(f" * {SPREAD}")} AS vec
                FROM generate_series(1, {DIM}) AS d(j) WHERE d.j + g.i > 0
            ) n
            """
        ),
        {"n": PROBE_QUERIES, "topics": TOPICS},
    ).scalars()
    return list(rows)


def _predicate(profile: Profile, owner: str) -> str:
    return f"({profile.sql.replace(':uid', repr(owner))})"


def _select(profile: Profile, owner: str) -> str:
    return (
        f"SELECT id FROM ann_spike WHERE {_predicate(profile, owner)}"
        " ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
    )


def _ground_truth(
    conn: sa.Connection, queries: list[str], profile: Profile, owner: str
) -> list[set[int]]:
    """Exact search: index scans disabled, so this is a full scan and a true top-k."""
    conn.commit()
    conn.execute(sa.text("SET LOCAL enable_indexscan = off"))
    conn.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
    truth = [
        set(conn.execute(sa.text(_select(profile, owner)), {"q": q, "k": K}).scalars())
        for q in queries
    ]
    conn.commit()
    return truth


def _measure(
    conn: sa.Connection,
    queries: list[str],
    truth: list[set[int]],
    profile: Profile,
    owner: str,
    *,
    iterative: str,
) -> Measurement:
    conn.commit()
    conn.execute(sa.text(f"SET LOCAL hnsw.iterative_scan = {iterative}"))

    scan = _scan_type(conn, queries[0], profile, owner)
    total = 0.0
    for query, expected in zip(queries, truth, strict=True):
        found = set(conn.execute(sa.text(_select(profile, owner)), {"q": query, "k": K}).scalars())
        total += len(found & expected) / max(1, len(expected))
    conn.commit()
    return Measurement(recall=total / len(queries), scan=scan)


def _scan_type(conn: sa.Connection, query: str, profile: Profile, owner: str) -> str:
    """What the planner actually did. Without this a seq-scan fallback reads as
    perfect recall, which is the most reassuring wrong answer available."""
    plan = conn.execute(
        sa.text(f"EXPLAIN (FORMAT JSON) {_select(profile, owner)}"),
        {"q": query, "k": K},
    ).scalar_one()
    if isinstance(plan, str):
        plan = json.loads(plan)
    nodes = _node_types(plan[0]["Plan"])
    if any("Index Scan" in n for n in nodes):
        return "hnsw"
    if any("Seq Scan" in n for n in nodes):
        return "seq"
    return "|".join(sorted(set(nodes)))[:10]


def _node_types(node: dict[str, object]) -> list[str]:
    found = [str(node.get("Node Type", ""))]
    children = node.get("Plans")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                found.extend(_node_types(child))
    return found


def _matching_rows(conn: sa.Connection, profile: Profile, owner: str) -> int:
    return int(
        conn.execute(
            sa.text(f"SELECT count(*) FROM ann_spike WHERE {_predicate(profile, owner)}")
        ).scalar_one()
    )


def _create_index(conn: sa.Connection, name: str, *, where: str | None) -> None:
    conn.execute(sa.text("SET maintenance_work_mem = '512MB'"))
    clause = f" WHERE {where}" if where else ""
    conn.execute(sa.text(f"CREATE INDEX {name} ON ann_spike {HNSW_OPTS}{clause}"))
    conn.commit()


# ── Environment ───────────────────────────────────────────────


def _extension_version(conn: sa.Connection) -> str:
    row = conn.execute(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    return str(row or "not installed")


def _server_version(conn: sa.Connection) -> str:
    return str(conn.execute(sa.text("SHOW server_version")).scalar_one())


def _has_random_normal(conn: sa.Connection) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT count(*) FROM pg_proc WHERE proname = 'random_normal'")
        ).scalar_one()
    )


def _teardown(conn: sa.Connection) -> None:
    conn.execute(sa.text("DROP TABLE IF EXISTS ann_spike"))
    conn.execute(sa.text("DROP TABLE IF EXISTS spike_centroid"))


def _say(message: str) -> None:
    """The script's only output. `print` is banned by ruff T20 for application
    code; a spike whose entire purpose is a table of numbers needs one exception,
    kept in one place."""
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
