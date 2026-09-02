# Milestone 5 — Documents, classification, indexing

**Status:** ✅ complete — **ready for validation**
**Date:** 18 August 2026 · 659 tests · CI green

Doc 07 M5: *"Done when a low-confidence document lands in L5 and the review queue, and nothing is silently visible."*
**You validate:** *"upload a payroll-like file; confirm it is not workspace-visible until reviewed."*

Two decisions were settled here and both are recorded: [ADR 0012](doc/adr/0012-one-hnsw-index-with-iterative-scan.md) (filtered-ANN strategy, by measurement) and the embedding boundary, which follows [ADR 0011](doc/adr/0011-the-language-model-is-optional.md)'s pattern.

---

## Acceptance

**Met.** `test_document_upload.py` asserts it at the level the route actually decides things, rather than by hand:

```
test_a_sensitive_document_is_not_workspace_visible_until_reviewed
  status               "indexed"
  chunks_indexed       0     <- nothing visible without a human decision
  chunks_held_for_review > 0
  every chunk          scope L5*, review_state NEEDS_REVIEW, owner = uploader
```

```
=== scripts: parse ===    PASS      === api: pytest ===   PASS  (659 tests)
=== api: ruff check ===   PASS      === web: tsc ===      PASS
=== api: ruff format ===  PASS      === web: lint ===     PASS
=== api: mypy strict ===  PASS      === web: build ===    PASS
CI GREEN
```

---

## Nothing is visible without a human decision

No classifier model exists yet (that is task 5.4's model, not its wiring), so **every chunk arrives with `classifier_failed` and withholds to L5 plus the review queue.**

That is not a stub standing in for the real thing. It is I4 working as specified: the absence of a classifier is a reason to **deny**, never a reason to default to visible. When the model lands it swaps in at one function and no caller changes.

`_classify_all()` is the seam. Today it sets `classifier_failed=True` on every input; the routing consequence — L5, owner = uploader, `NEEDS_REVIEW` — is decided by `classify_chunk`, which is already the real implementation.

## The review queue cannot be used to escalate

`POST /documents/review-queue/{chunk_id}` **refuses to approve a chunk into a scope the reviewer could not read themselves** (`scope.may_reach_scope(target)`).

Without that check the queue is a privilege-escalation route: withhold a chunk to L5, then promote it to L2 from an account that cannot read L2 at all. The reviewer's own reach is the ceiling on what they can grant.

## First production caller of `scoped_connection`

The architecture calls `scoped_connection` the mandatory path for customer data, and a backend audit found it had **zero** callers. `_record()` is the first.

That matters beyond convention: the GUCs it sets are what the `WITH CHECK` half of the isolation policy reads, so a bug aiming these rows at another workspace is refused by Postgres rather than by our own care. Document and chunks go in **one transaction** — a partial write would leave a document claiming `indexed` with only part of its content reachable, which is the silent-failure shape doc 07 forbids.

## Failure is visible, and the kinds are distinguished

| Case | Result |
|---|---|
| Scanned PDF, no text layer | `status: failed`, reason persisted and returned |
| Unsupported type | `state: quarantined` — a different action (convert, not re-save) |
| Empty file | 400, nothing stored |
| Oversize | 413, **stating the limit** rather than implying it |
| No consent | 400, nothing stored |

Silence here is worse than an error: the customer believes the document is searchable and finds out when an answer omits it, which reads as the product being wrong rather than the upload having failed.

## Task 5.7 — the spike, and what it cost

**Answer: one HNSW index and an ordinary predicate, with `hnsw.iterative_scan = relaxed_order`.** Partial indexes per scope are not needed. ADR 0012 has the full table; the load-bearing row:

```
L5 own rows only   400 rows    plain 5.0%    iterative 98.0%    partial 100.0%
```

Plain HNSW fails hardest exactly where this product's permission model bites most often. At Contributor selectivity it returns 5% of the right rows — nineteen of every twenty of the user's own documents missing from an answer that reads as complete. **Raising `ef_search` looks like the fix and is not:** it rescues a department-sized filter (47% → 98%) and leaves the narrow cases broken (5% → 17%).

**The first version of this spike produced a plausible table that measured nothing**, and that is the more useful finding. Four causes, each invisible in the output: isotropic vectors that floor every strategy equally; two of four rows that were seq scans reported as recall; an unrecorded `ef_search`; and a concurrent session holding an `ann_spike` table of its own shape, so ground truth and measurement could come from different contents. All four are written into the script's docstring, because someone will re-run this against real embeddings and those are the traps to avoid.

## Task 5.6 — the embedding boundary

`fastembed` and the ~2GB `multilingual-e5-large` weights are an **optional extra**. Without them documents still upload, parse, classify and reach the review queue; chunks are stored with a NULL embedding — a state migration 0007's provenance constraint already permits — and `/health/ready` reports `embeddings: unconfigured` as its own check, separate from `pgvector`, because the extension being present must not read as "search works".

**The no-fake rule is stricter here than for the language model, deliberately.** A scripted LLM provider refuses and fails loudly. A hash-derived embedding does not fail — it *ranks*, producing confident citations beside a real answer with no symptom on screen. So `DeterministicEmbedder` is unreachable from configuration and a test asserts no setting can select it.

The pass writes **only** the embedding columns. A test asserts the UPDATE never mentions `scope`, `review_state`, `sensitivity`, `owner_user_id` or `department`: the job that makes documents searchable must not also be able to promote a withheld one with no review record.

---

## What does not exist

- **No classifier model.** Everything withholds. Correct by I4, but it means the review queue is the only path to visibility today.
- **No retrieval.** That is M6, and ADR 0012 is its input.
- **No OCR** (assumption A7). A scanned PDF fails visibly rather than being indexed as empty.
- **No embedding model installed here.** The pass is scheduled and correct; it reports `unconfigured` and does no work until `pip install -e ".[embeddings]"`.
- **The embedding pass runs in the API process.** Free while the model is absent by default; ~2GB resident in the request-serving process once it is not. It belongs in a separate worker at that point.

---

## How to validate

```powershell
.\scripts\verify.ps1
```

The suites carrying the acceptance:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest tests\test_document_upload.py tests\test_classification_default_deny.py tests\test_embedding_boundary.py tests\test_embedding_pass.py -v
```

To re-run the spike (~15 minutes against Neon; it namespaces its own table):

```powershell
cd services\api
.\.venv\Scripts\python.exe ..\..\scripts\spike_ann_recall.py
```

**The most useful thing you can do is upload a real payroll file** and confirm it is not workspace-visible. The second most useful is to disagree with the review queue's escalation ceiling: today a Manager cannot approve a chunk to L2. If that is wrong for your customers it should change as an ADR, not an edit.

---

## Invariants

| | Status |
|---|---|
| **I1** never invent a number | Untouched here — no figures are produced by this milestone |
| **I2 / I3** scoped retrieval | `_record` writes through `ScopedSession`; the query predicate arrives in M6, its strategy fixed by ADR 0012 |
| **I4** default-deny on classification | Structural: no classifier ⇒ every chunk withholds. Asserted, not assumed |
| **I10** never a zero, never a blank | A failed upload returns a reason; `chunks_indexed: 0` is paired with `chunks_held_for_review` and a message |

---

## Next

**M6 — retrieval.** Its design question is already answered: a single HNSW index with the permission predicate in the `WHERE`, and `hnsw.iterative_scan = relaxed_order` set on the retrieval path.

Two things to settle before it ships:

1. **`hnsw.max_scan_tuples` defaults to 20,000** — the size of the entire spike table. It bounds an iterative scan's effort, so ADR 0012's figures say nothing about production cardinality. Re-run 5.7 at scale.
2. **Recall is 88–99%, not 100%.** That affects which chunks are cited, not whether a number is right: I1 requires figures to be computed from database rows by `calculators/`, never from retrieved text. Worth keeping distinct, because the two failure modes are easy to conflate.
