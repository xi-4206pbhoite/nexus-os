# Continue here

Written at the end of a session that reached Phase 10. **Start by reading
`GOAL-STATUS.md`** — it says what works and what is simulated. This file is only
the mechanics of picking the work back up.

## Prove the state before changing anything

```bash
services/api/.venv/bin/python scripts/goal_walkthrough.py
```

59 checks against a running API. It is re-runnable, and **five of its checks
exist because a re-run is different from a first run** — a known address gets no
second verification email, a second acceptance is refused, and a member placed
earlier is in that run's company. If one of those goes red, read it as the
product being right before assuming a regression.

The API must be on `127.0.0.1:8001`:

```bash
cd services/api && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## The next work, in order

**Finish P10** before starting P11 — the plan makes everything after it depend
on the retrieval core, and two items remain:

- **A recall test that discriminates.** `evals/test_recall_regression.py`
  asserts recall is high but does **not** fail when `SET LOCAL
  hnsw.iterative_scan` is removed. Two attempts are recorded in the file; the
  missing ingredient is corpus size, not the query plan. Needs tens of thousands
  of rows so the HNSW graph is deep enough for the permission filter to exhaust
  a traversal — which is the mechanism ADR 0012's 5% comes from.

  **Three attempts are recorded in the file, and the third names the real
  obstacle**: 20k rows generated server-side got past the server's
  `statement_timeout` and straight into asyncpg's client timeout. Building
  20k × 1024-dimension vectors across a link to `us-east-1` is minutes per run.
  Do it against the local container (`scripts/db-ci.ps1`, ~25s versus Neon's
  ~5min), where the inserts are cheap and no timeout is in the way. It is an
  hour's work on the right machine and was unreachable from the wrong one.
- **`[embeddings]` in CI.** ~2 GB of weights per run. Worth it only if the
  question is whether `multilingual-e5-large` places similar text near each
  other — which is a different question from the index behaviour above, and
  should be a separate, non-blocking job.

**P11 has four pieces in**: the source state machine (Q56 — one source failing
never fails the run), the worker's `FOR UPDATE SKIP LOCKED` claim with reclaim
of orphaned runs (Q50), the progress API (Q57 — never one spinner), and the
quota (Q55). The crawl **planning** is in too — `app/research/site.py` has priority ordering,
de-duplication, the 20-page budget, the soft/hard caps and JavaScript-shell
detection, all pure and tested without a network.

What remains is the **orchestration that joins them**: seed from
`workspace.domain` plus `workspace_url` rows, fetch `sitemap.xml` then fall back
to links, drive `fetch_page` over `plan()`'s output under `Budget`, and write
each source's outcome independently. Every fetch already goes through the SSRF
guard re-validated per hop — that is `fetch_page`, and it should not be
reimplemented.

**Then the rest of P11** and **P12** (classification, 8 days).
P13's brain already exists but assembles directly from `onboarding_answer`; when
the retrieval core is finished it should read through the scoped path instead.

## Things that will bite you

- **The suite takes ~20 minutes against Neon from a laptop** and ~1m40s in CI
  against a local Postgres. Run targeted files locally; **CI is the gate.**
  Every full-suite claim in this repo is a CI claim.
- **Docker is in WSL on the Windows host**, not on macOS. The composed stack can
  only be exercised by pushing — the E2E job builds and runs it.
- **The `.claude/launch.json` change is deliberately unstaged.** It is local
  editor config.
- **A test that uses `TestClient` must be `sync`, not `async`.** `TestClient`
  drives its own event loop and an asyncpg connection is bound to the loop that
  opened it, so a pooled connection left over from an outer loop surfaces as
  *"attached to a different loop"* from inside Starlette's middleware — an error
  naming neither the pool nor the fixture. Do async setup in `asyncio.run()` and
  `await get_engine().dispose()` before the client starts.
  `tests/test_research_progress.py` shows the shape. Every other TestClient test
  in the repo is sync for this reason; it cost two attempts to rediscover.

- **`scoped_connection` and the three `apply_*_scope` functions are the only
  places any `nexus.*` GUC is set.** `test_scoping_primitive_containment`
  asserts an empty allowlist; if you need a fourth, that means a new kind of
  scoping exists and is a decision to make deliberately.

## Still needs Parul

- **Rotate the Neon credential `npg_2sQGXiOzueB7`.** It has been in a
  conversation log since P5.
- **Finding #17** — whether a rolling session gets an absolute cap.
- **The 21 document asks** in `app/domain/document_asks.py` are provisional; 19
  of them are drafted rather than specified. The tests assert their
  *properties*, never their wording, so editing the text breaks nothing.
- **D4** — a real email provider for production. CI has a Mailpit sink; a
  deployment does not.
