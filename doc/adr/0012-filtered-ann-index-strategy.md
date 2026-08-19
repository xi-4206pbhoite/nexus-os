# ADR 0012 — Index strategy for filtered ANN retrieval

- **Status:** Accepted
- **Date:** 18 August 2026
- **Decides:** task 5.7, which doc 07 M5 makes a precondition for M6
- **Measured on:** Neon serverless Postgres 18.4, pgvector 0.8.6, `us-east-2`

## Context

I3 requires the permission predicate to be evaluated *inside* the vector query, not
applied to its results. Post-filtering leaks through ranking, result counts and
latency, and migration 0007 put every scope field on the chunk row specifically so
the predicate could be an ordinary `WHERE` clause in the ANN query.

That leaves one open question, and `ARCHITECTURE.md` §3.3 flags it as needing
measurement before M6 relies on it: an HNSW search walks a graph built over *all*
rows, so a selective filter can leave the walk returning fewer than `k` matching
rows, or missing the true nearest ones. Two candidate designs:

1. **One HNSW index plus a `WHERE` clause.** One index, no maintenance beyond the
   ordinary. Recall is the risk.
2. **Partial indexes per scope.** Every row in the index already satisfies one
   filter, so recall is good by construction. But the index count multiplies with
   scopes × departments, and a chunk whose scope changes at review has to move
   between indexes — on a table where review is routine, since I4 routes every
   unclassifiable chunk through it.

M6's predicate is a **four-branch disjunction** over `scope`, `department[]` and
`owner_user_id`. A disjunction cannot become an index condition; it can only be a
filter applied to rows the graph walk already returned. That is the mechanism under
test, so `scripts/spike_ann_recall.py` measures the role → scope profiles of doc 06
§2.3 rather than abstract selectivities.

## The first run was wrong, and wrong in a way worth recording

The spike had never been executed — it generated 20,000 × 1024-dimensional vectors
client-side and inserted them row by row, roughly 400 MB of pgvector text form
shipped to `us-east-2`. Once it was made to run (generation moved inside Postgres),
its first results contradicted themselves:

```
Owner (all depts)   90.0% selectivity    plain  9.2%   partial 10.0%
Own L5 only         10.0% selectivity    plain 100.0%  partial 64.2%
```

An Owner matching 90% of rows cannot score 9.2%, and `partial` is defined as the
upper bound so it cannot be lower than `plain`. Two measurement defects, both of
which produce a *confident* wrong answer rather than an error:

**Independent gaussian vectors have no neighbourhoods.** Measured on this database:
in 1024 dimensions the mean cosine distance is 0.9977 and the nearest of 300 rows
is only 3.0 sd below it. The true top-10 is therefore an arbitrary pick among
thousands of near-ties, so recall@10 measures tie-breaking — and necessarily gets
*worse* as more rows match, which is exactly the inverted pattern above. The corpus
is now drawn around 250 centroids, giving **13.8 sd of separation**, and the script
aborts below 5.0 rather than reporting numbers that cannot mean anything.

**The chosen plan has to be recorded, not assumed.** At 10% selectivity Postgres
abandoned the HNSW index for a sequential scan — which is *exact*, so it scored
100% while measuring nothing about the index. A seq-scan fallback presenting as
perfect recall is the most reassuring wrong answer this spike could produce. Every
figure now carries its scan type from `EXPLAIN`.

Both fixes are the same discipline `db/bootstrap.sql` already applies to Neon's
`ALTER ROLE`: tolerate the statement, prove the outcome.

## Measurement

```
20,000 rows · 1024 dimensions · 250 clusters · spread 0.45
HNSW m = 16, ef_construction = 64 · recall@10 vs exact search · 8 probe queries
```

```
caller profile                rows    sel          plain      iterative        partial
--------------------------------------------------------------------------------------
Owner (all depts)           18,000 90.0%    100.0% hnsw    100.0% hnsw    100.0% hnsw
Dept Manager (1 of 6)        8,667 43.3%     68.8% hnsw    100.0% hnsw     86.2% hnsw
Contributor (restricted)     8,667 43.3%     68.8% hnsw    100.0% hnsw     87.5% hnsw
Viewer (L1+L2)               7,000 35.0%     62.5% hnsw     98.8% hnsw     96.2% hnsw
Own L5 only                  2,000 10.0%    100.0%  seq    100.0%  seq     78.8% hnsw
```

Four things in that table matter, and one of them was not anticipated.

**Plain HNSW plus a `WHERE` clause is not good enough in the middle band.** 62–69%
recall at 35–43% selectivity means roughly a third of the genuinely nearest chunks
are missing from a grounded answer, with nothing to indicate it. For a product whose
position is that every figure traces to a source, silently retrieving two thirds of
the relevant evidence is a grounding defect, not a performance one.

**`hnsw.iterative_scan = relaxed_order` fixes it completely.** 98.8–100% across
every profile where the index is used. This is the whole decision.

**The narrow end is safe because the planner stops using the index.** At 10%
selectivity Postgres chose a sequential scan, which is exact. That is where *every
chunk sits today* — I4 withholds everything to L5 for want of a classifier — so the
current corpus is served exactly, by the optimiser's own cost estimate rather than
by anything we arranged.

**Partial indexes measured *worse* than the single index with iterative scan**
(78.8–96.2% against 98.8–100%), which inverts the assumption in
`ARCHITECTURE.md` §3.3 that they are the upper bound. The explanation is that a
partial index is a *smaller graph built with the same* `m` *and* `ef_construction`,
so it carries its own approximation error, and nothing makes it keep searching for
more matches. "Fewer rows in the index" is not the same as "better recall".

## Decision

**One HNSW index over the whole `chunk` table, plus the ordinary disjunctive
predicate, with `hnsw.iterative_scan = relaxed_order` set on the session.**

Partial indexes per scope are **rejected**. They measured worse, and they would have
cost an index count multiplying with scopes × departments plus a re-indexing step
every time the review queue changes a chunk's scope — routine work, since I4 sends
every unclassifiable chunk through review.

So M6 keeps the design `ARCHITECTURE.md` §3.3 describes. Nothing about the schema
changes; migration 0007's HNSW index stands as built.

## Consequences

**M6's first task is to set the GUC in `app/retrieval/scoped.py`.** It belongs
beside the two `set_config` calls already there, transaction-scoped for the same
reason they are: `scoped_connection` is the only path to workspace data, so setting
it there is the one place no query can forget. Deliberately **not** done in this
milestone — `relaxed_order` changes result-ordering semantics for every vector query
in the system, and that is M6's decision to take with its eyes open rather than a
side effect of a spike.

**`strict_order` is untested.** Only `relaxed_order` was measured. Relaxed ordering
may return results slightly out of distance order, which is harmless when the top-k
becomes context for a model and less harmless if a screen labels one chunk "closest
match". If ordering turns out to matter for display, `strict_order` needs its own
measurement — it recovers less recall by design.

**`hnsw.max_scan_tuples` becomes a real limit.** Iterative scan keeps searching, so
it bounds the work; the default is 20,000 tuples, which is the size of this entire
corpus. At production cardinality that ceiling, not the graph, may decide recall for
the narrowest predicates. Worth watching when a workspace passes ~100k chunks.

**The measurement is optimistic and should not be quoted as a production figure.**
Synthetic clusters separate more cleanly than real e5 embeddings. What transfers is
the comparison between columns at equal selectivity and the plan the optimiser
chose, not the absolute percentages.

## Revisit when

- The chunk table passes roughly 100,000 rows in a single workspace, or when a
  workspace's own corpus becomes large enough that the planner's cost estimates
  shift away from what was measured here.
- The embedding model changes. Real e5 vectors cluster differently from synthetic
  centroids, and this measurement is optimistic about separability — `/evals/grounding`
  (M8) should carry retrieval-quality cases so the next decision uses real
  embeddings rather than a synthetic corpus.
- pgvector's iterative scan implementation changes; it is new in 0.8.
