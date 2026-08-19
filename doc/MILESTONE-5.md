# Milestone 5 — Documents, classification, indexing

**Status:** ✅ complete — **ready for validation**
**Date:** 18 August 2026 · 681 tests · `mypy app` clean

Doc 07 M5: *"Done when a low-confidence document lands in L5 and the review queue,
and nothing is silently visible."*
Validation: *"Upload a payroll-like file; confirm it is not workspace-visible until
reviewed."*

Tasks 5.0–5.5 and 5.8–5.10 landed on 18 August. This note covers the two that were
open — **5.6 embedding into pgvector** and **5.7 the filtered-ANN recall spike** —
and the four defects finishing them uncovered.

---

## Acceptance

**Met.** And now met against a real database on the write path, which it was not
before: three of the four defects below made the M5 upload path unable to store a
single chunk in Postgres.

```
api: ruff check         PASS      api: pytest (hermetic)   PASS  (554 tests, 5s)
api: ruff format        PASS      api: pytest (Neon, new)  PASS  (6 tests, 67s)
api: mypy app --strict  PASS      47 tests added by 5.6 / 5.7
```

---

## 5.6 — Embedding, and what `indexed` is allowed to mean

### The defect this task really fixed

The upload route wrote `status = 'indexed'` unconditionally, before any embedder
existed. `indexed` is the product's claim that content is retrievable, and nothing
downstream re-checks it — so the status was a promise nothing kept. A customer
would have discovered it when a Proposal Studio output silently omitted a price
they had uploaded, which reads as the product being wrong rather than the upload
being incomplete.

`document.status` now distinguishes the two honestly:

| Status | Means |
|---|---|
| `indexed` | Every chunk carries a vector. Retrievable. |
| `parsed` | Stored, chunked, classified, reviewable — **not searchable**, and the response says why |

There is no partial state. If the embedder returns fewer vectors than there are
chunks, or vectors of the wrong width, the whole document stays `parsed`: writing
the ones that worked would leave a document searchable in part with nothing to
indicate which part.

### The embedding boundary

`app/embedding/` mirrors `app/ai/` — a protocol, a registry that decides from
configuration, and providers behind it. Nothing outside the package knows which
model runs, so a swap is a registry change and not a refactor (ADR 0003 stores
`embedding_model_id` and `embedding_dim` per chunk row for exactly that).

```
contracts.py            Embedder protocol · EmbeddedText · availability states
providers.py            UnconfiguredEmbedder (refuses) · DeterministicEmbedder (tests)
fastembed_provider.py   multilingual-e5-large, 1024d, CPU, lazily loaded
registry.py             the one place that chooses — and refuses the test double
```

Three decisions are worth stating because each is a product constraint rather than
a style preference.

**`query: ` and `passage: ` are applied in one place.** ADR 0003 requires it and
the interface enforces it structurally: there is no `embed(text)` on the protocol,
only `embed_passages` and `embed_query`. Getting e5's prefixes wrong does not
error — retrieval keeps returning rows, just worse ones, by an amount nobody
notices until grounding quality is measured.

**No embedder is a supported state, not a broken one** (ADR 0011's pattern).
`NEXUS_EMBEDDING_BACKEND` defaults to `none`, `fastembed` is an optional extra, and
`/health/ready` reports `embeddings` alongside `language_model`. Documents still
upload, parse, classify and queue for review.

**The deterministic test double is refused outside `local` and `ci`** — not
discouraged, refused, with `/health/ready` reporting `error`. This is the one place
this layer is stricter than `app/ai/registry.py`, and deliberately:
`app/ai/providers.py` argues that a demo mode returning plausible analysis would be
the most damaging thing in the codebase. The retrieval equivalent is worse because
it is quieter — well-formed, stable, correctly-sized vectors with no semantic
structure. Every mechanism works. Vectors store, the index builds, queries return
the right number of rows at plausible distances, citations render. The results are
noise, nothing fails, and nothing is labelled.

### Embedding is not a visibility decision

Every chunk is embedded, **including the ones I4 withholds to L5**. A vector does
not make a chunk reachable — the scope predicate does (I3). Leaving withheld chunks
unembedded would mean approving one in the review queue silently did half its job,
since it would then need re-embedding before anyone could find it.

The response therefore reports two numbers that are routinely different:

```json
{ "status": "indexed", "chunks_embedded": 41, "chunks_indexed": 0,
  "chunks_held_for_review": 41, "searchable": true }
```

Today every chunk withholds — no classifier exists — so a fully embedded document
is fully invisible. One number for both would read as *"41 chunks are available to
your team"*, which is false.

`test_document_indexing.py::test_embedding_does_not_change_scope_or_review_state`
is the assertion that keeps this true.

### What is deliberately not built

**Indexing runs inline, in the request.** It keeps the document and its vectors in
one transaction, so no document is ever momentarily `indexed` with nothing to
retrieve. The cost is latency proportional to document length — a 300-chunk PDF on
CPU is seconds, not milliseconds. Moving it to `jobs/` needs a status the UI polls
and a retry path, which is a larger change than 5.6 and belongs with M6's
throughput requirements. Flagged rather than silently built.

**No classifier.** Task 5.4's gate is complete and every input still arrives with
`classifier_failed=True`, so everything withholds. That is I4 working, not a gap.

**No re-embedding job.** `embedding_model_id` per row makes a future model change
identifiable; nothing yet acts on it.

**No upload UI.** `POST /documents` and the review-queue endpoints are the only
surface; `apps/web` has no document screen, so validation step 2 below is an API
call. The `searchable` / `chunks_embedded` / `message` fields exist so that screen
can render the `parsed` state honestly when M5's UI is built — the seven render
states of doc 06 §7.1 need `parsed` to be distinguishable from `indexed`, and it
would have been unrepresentable if the route kept claiming `indexed`.

---

## 5.7 — The filtered-ANN recall spike

See [ADR 0012](adr/0012-filtered-ann-index-strategy.md) for the decision and the
full numbers.

The question M6 could not be designed without: pgvector must apply the permission
predicate *inside* the vector query (I3), and an HNSW search walks a graph built
over all rows — so a selective filter can leave the walk returning far fewer than
`k` matching rows, or missing the true nearest ones. One index plus a `WHERE`, or
partial indexes per scope?

**The script had never been run.** It generated 20,000 × 1024-dimensional vectors
client-side and inserted them a row at a time — roughly 400 MB of pgvector text
form shipped to `us-east-2`. It now generates them inside Postgres with
`random_normal()` in one statement, and asserts that 99% of the vectors are
distinct before trusting any figure: if the planner had hoisted the volatile
subquery, every row would share one vector and every recall number would be
meaningless but entirely plausible.

It also now filters on **M6's actual predicate** rather than a single random float.
That matters more than selectivity: the real predicate is a four-branch disjunction
over `scope`, `department[]` and `owner_user_id`, and a disjunction cannot become
an index condition — it can only be a filter applied to rows the graph walk already
returned. That is the mechanism under test, so the profiles are the role → scope
rows of doc 06 §2.3: Owner, Department Manager, restricted Contributor, Viewer, and
own-L5-only, which is where every chunk sits today.

### The first run's numbers contradicted themselves

Worth recording, because both defects produce a *confident* wrong answer:

```
Owner   90.0% selectivity   plain   9.2%   partial  10.0%
Own L5  10.0% selectivity   plain 100.0%   partial  64.2%
```

An Owner matching 90% of rows cannot score 9.2%, and `partial` was defined as the
upper bound so it cannot come in below `plain`. The causes were mine, not pgvector's:
**1024 independent gaussians have no neighbourhoods** (mean cosine distance 0.9977,
nearest of 300 rows only 3.0 sd below it — so recall@10 measured tie-breaking, which
gets *worse* as more rows match), and **the script never checked which plan ran** (at
10% selectivity Postgres switched to a sequential scan, which is exact, so it scored
100% while measuring nothing).

The corpus is now clustered — 13.8 sd of separation, asserted before any figure is
trusted — and every number carries its scan type from `EXPLAIN`.

### The answer

```
caller profile                rows    sel          plain      iterative        partial
Owner (all depts)           18,000 90.0%    100.0% hnsw    100.0% hnsw    100.0% hnsw
Dept Manager (1 of 6)        8,667 43.3%     68.8% hnsw    100.0% hnsw     86.2% hnsw
Contributor (restricted)     8,667 43.3%     68.8% hnsw    100.0% hnsw     87.5% hnsw
Viewer (L1+L2)               7,000 35.0%     62.5% hnsw     98.8% hnsw     96.2% hnsw
Own L5 only                  2,000 10.0%    100.0%  seq    100.0%  seq     78.8% hnsw
```

**One HNSW index and an ordinary predicate, with `hnsw.iterative_scan =
relaxed_order`.** Plain HNSW loses roughly a third of the nearest chunks in the
35–43% band — a grounding defect, not a performance one, since a silently
two-thirds-complete evidence set is exactly what I1 exists to prevent. Iterative
scan recovers 98.8–100%.

Two results were not anticipated. **Partial indexes measured *worse*** (78.8–96.2%),
inverting `ARCHITECTURE.md` §3.3's assumption that they are the upper bound: a
partial index is a smaller graph with the same `m` and `ef_construction`, so it has
its own approximation error and nothing makes it keep searching. And **the narrow end
is safe because the planner abandons the index** for an exact scan — which is where
every chunk sits today, since I4 withholds everything to L5.

---

## Found by running it, not by testing it

Two things only a live run against the real model could surface.

**`embedding_model_id` was not enough to identify what needs re-embedding.**
fastembed 0.8.0 embeds `multilingual-e5-large` with **mean pooling**; 0.5.1 used
the CLS token. Different vectors, identical model name, announced only in a
`UserWarning` at load time. Vectors from the two do not share a space, so mixing
them degrades retrieval silently rather than failing — which is precisely the
situation ADR 0003 stores this column to prevent. The provenance is now
`intfloat/multilingual-e5-large@fastembed-0.8.0`.

Worth noting the near miss: `pyproject.toml` sets `filterwarnings = ["error"]`, so
that warning *would* have failed a test — but no test loads the real model, they
all use the deterministic double. The double is what makes CI fast and is the right
default; it also means this class of upstream change is invisible to the suite.

**The chunker merges short documents, as designed.** A three-topic, 250-character
document became **one** chunk (`TARGET_CHARS = 1200`), so every semantic probe
returned the same row. Not a defect — but it means a real retrieval eval needs
documents past the chunk threshold, which `/evals/grounding` (M8) should build in
rather than discover.

---

## Defects found finishing this milestone

Recorded in full in `AUDIT-FINDINGS.md`. Summarised because three of the four made
the M5 write path non-functional against a real database:

| Defect | Effect |
|---|---|
| `ReviewState.NEEDS_REVIEW = "needs_review"` vs a CHECK allowing `pending_review` | **No chunk could ever be inserted.** Every chunk withholds through this member |
| `status = 'superseded'` not in `ck_document_status` | Superseding rolled back the replacement — a new price list could not be uploaded |
| `beautifulsoup4` / `lxml` imported but undeclared | Clean clone failed to collect 10 test modules |
| `sqlalchemy` without the `asyncio` extra, so no `greenlet` | 29 errors across 4 modules, presenting as a database outage |

**All four were invisible for the same reason**, and it is the reason recorded twice
already in `AUDIT-FINDINGS.md`: `tests/test_document_upload.py` substitutes
`_record`, so the suite asserted the shape the route *meant* to write rather than
the shape Postgres accepts — and the venv running the gate was never rebuilt from
the manifest it is supposed to describe.

Two countermeasures, both structural rather than diligence-based:

- **`tests/test_chunk_embedding_roundtrip.py`** writes real chunks with real vectors
  as `nexus_app`, using the production spelling of every value
  (`ReviewState.NEEDS_REVIEW.value`, `EmbeddedText.to_sql_literal()`). It *iterates*
  `ReviewState` rather than listing it, so a future member the constraint rejects
  fails immediately.
- **The manifest is now the only source of the environment.** Both missing
  dependencies were found by building a venv from `pyproject.toml` and nothing else.

---

## Raised for M6, not decided here

**Setting `hnsw.iterative_scan` is M6's first task, not this milestone's.** It
belongs beside the two `set_config` calls in `app/retrieval/scoped.py` — the only
path to workspace data, so the one place no query can forget it. Left undone
deliberately: `relaxed_order` changes result-ordering semantics for every vector
query in the system, and that is a decision to take deliberately rather than absorb
as a side effect of a spike. `strict_order` was not measured.

**`ARCHITECTURE.md` §3.3 filters on `review_state != 'quarantined'`, a value the
chunk constraint has never allowed.** As written the clause matches every row, so
it is not a filter at all. Quarantine is a *document* state — `document.status`
carries it for an unsupported file type — so what M6's predicate should exclude at
the chunk level is a genuine question: `pending_review` and `rejected` are the
candidates, and whether an uploader can retrieve their own pending chunk is a
product decision rather than an obvious fix. Not invented here; it goes to M6 with
this note.

---

## You validate

1. `.\scripts\ci.ps1` — the gate. Note it now installs `greenlet` and `bs4`
   transitively; if your venv predates this, rebuild it with `.\scripts\setup.ps1`.
2. **Upload a payroll-like file with no embedder configured.** It returns
   `status: parsed`, `searchable: false`, and a message saying it is stored and
   reviewable but not searchable. Confirm it is not workspace-visible.
3. **Add `NEXUS_EMBEDDING_BACKEND=fastembed` to `.env`**, then in `services\api` run
   `pip install -e ".[embeddings]"`. First upload downloads ~1.1 GB to `models\`.
   Re-upload: `status: indexed`, `chunks_embedded` matches the chunk count, and
   `chunks_indexed` is still `0` — embedded, and still withheld.
4. `/health/ready` reports `embeddings`. Set `NEXUS_EMBEDDING_BACKEND=deterministic`
   with `NEXUS_ENV=production` and confirm it reports `error`, not `ok`.
5. Read `ADR 0012` and disagree with the index decision if the numbers do not
   support it.
