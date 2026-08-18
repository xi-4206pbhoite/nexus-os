# ADR 0012 — One HNSW index with `iterative_scan`, not partial indexes per scope

**Status** Accepted
**Date** 2026-08-18
**Decided by** Measurement (task 5.7). No product judgement was required.

## Context

I3 requires the permission predicate to be applied *inside* the vector query,
never as a filter over results that have already been ranked. In pgvector there
were two candidate shapes for that, and M6's design differs materially between
them:

1. **One HNSW index plus an ordinary `WHERE`.** Simple. But an HNSW search walks
   a graph built over *all* rows, so a selective filter can leave the walk
   returning far fewer than `k` matching rows, or missing the true nearest ones.
2. **Partial indexes per scope.** Every row an index contains already satisfies
   the filter, so recall is good by construction. The cost is that the number of
   indexes multiplies with scopes × departments, and a chunk whose scope changes
   at review has to move between indexes — a re-indexing path M6 would have to
   own.

Doc 07 M5 task 5.7 exists precisely to decide this by measurement rather than by
preference.

## Measurement

`scripts/spike_ann_recall.py`, against Neon (pgvector 0.8.6): 20,000 rows ×
1024d, 40 topic clusters at noise sd=0.05, `k=10`, 10 probe queries, HNSW
`m=16, ef_construction=64`. Recall is against exact search over the same rows,
with index use forced so that every cell is genuinely an ANN result.

```
filter                  rows          ef=40                   ef=100
                             plain    iter  partial   plain    iter  partial
L2 company-wide       12,000  97.0%  97.0%  100.0%   100.0%  100.0%  100.0%
L3 one department      3,000  47.0%  99.0%  100.0%    98.0%   99.0%  100.0%
L5 own rows only         400   5.0%  98.0%  100.0%    17.0%   99.0%  100.0%
L5, very narrow          100   5.0%  88.0%  100.0%    12.0%   89.0%  100.0%
```

`partial` at 100% throughout is the harness's own sanity check: an index
containing only the matching rows must score perfectly, and a version of this
spike that reported 23% there was measuring something else (see *Provenance*).

## Decision

**M6 uses a single HNSW index over the chunk table with the permission predicate
as an ordinary `WHERE`, and sets `hnsw.iterative_scan = relaxed_order` on the
retrieval path.** Partial indexes per scope are not built.

## Why

- **Plain HNSW fails hardest exactly where this product's permission model bites
  most often.** At the selectivity of a Contributor reading their own rows,
  recall is 5%. Nineteen of every twenty of the user's own documents would be
  silently absent from an answer that reads as complete. Narrow scopes are the
  normal case here, not an edge.
- **`iterative_scan` recovers it** — 88–99% across every selectivity tested —
  without multiplying indexes and without a re-indexing path when review changes
  a chunk's scope.
- **Raising `ef_search` is not a substitute, and looks like one.** It fixes the
  department-sized filter (47% → 98%) and leaves the narrow cases broken (5% →
  17%, 5% → 12%). Anyone who tested the obvious knob against a department-scoped
  query would conclude the problem was solved.

## What this does not settle

- **`hnsw.max_scan_tuples` defaults to 20,000**, which is the entire size of the
  test table. The cap is what bounds an iterative scan's effort, so these figures
  say nothing about behaviour once a workspace exceeds it. Re-run 5.7 at
  production cardinality before M6 ships.
- **`relaxed_order` means results are not in exact distance order.** Acceptable
  for retrieval feeding a grounded answer; if anything downstream ever needs a
  true ranking, `strict_order` is the alternative and its cost is unmeasured.
- **Recall is 88–99%, not 100%.** That affects which chunks are cited, not the
  correctness of any figure: I1 requires numbers to be computed from database
  rows by `calculators/`, never from retrieved text. A retrieval miss makes an
  answer less complete; it cannot make a number wrong. Worth stating because the
  two failure modes are easy to conflate.
- **Permissions are drawn independently of topic** in the spike, which is the
  realistic case. Correlated permissions — a department whose documents are also
  topically clustered — would be a separate run.
- **The vectors are synthetic.** Task 5.6 brings real embeddings; re-running 5.7
  against them is cheap and worth doing.

## Provenance

The first version of this spike produced a table that looked like an answer and
was not one, and three of its defects are recorded in the script's docstring
because each was invisible in the output: uniformly random vectors are isotropic
in 1024d and floor every strategy equally; two of four rows were seq scans
reported as recall; and `ef_search` — the knob that governs the whole question —
was never recorded.

A fourth cause was environmental: a concurrent session held a 20,000-row
`ann_spike` table of its own shape, creating and dropping indexes on it, while
the first run measured a table of the same name. Ground truth and measurement
could therefore be taken against different contents. The spike now namespaces
its table and indexes per process. The test suite was checked and is not exposed
— every test runs in a transaction that is always rolled back, with fresh UUIDs
throughout — but ad-hoc scripts doing DDL under fixed names on a shared database
are, and that is a general hazard here rather than a one-off.
