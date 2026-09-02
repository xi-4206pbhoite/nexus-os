# NEXUS OS — Build Status

**Regenerated:** 3 September 2026, at the end of **Phase 0** of
`doc/12-IMPLEMENTATION-PLAN.md`.
**Method:** every claim below was run, not read. Where a figure is quoted, the
command that produced it is named.

---

## 1. Where this stands

**~32% of the product.** Phase 0 did not change that number and was not meant
to: it built no product surface. What it changed is whether the number can be
trusted — and whether the next twenty-one phases can be.

| | Before Phase 0 | After |
|---|---|---|
| Database tests in CI | **94 skipped, exit 0** | 664 executed, exit 0 |
| Row-level security proved automatically | no | yes — 12 isolation tests, executed |
| Migrations ever run in reverse | no | yes, every run: `upgrade → downgrade base → upgrade` |
| `mypy --strict` over `tests/` | no | yes, 101 files clean |
| Coverage measured | no | 74.21% branch, with a floor |
| A skipped database test | invisible | fails the build, by name |

The engineering foundation was already strong for this stage and almost none of
the product is reachable by a user. That split is unchanged. The 🔴 defects in §4
are the same ones, and Phase 1 is where they get fixed.

| Area | Complete | Basis |
|---|---|---|
| Foundation — repo, config, logging, health, CI, migrations | **95%** | CI now runs against real Postgres, both directions. Gaps: no-op secret validator, no DB timeouts — both Phase 1 |
| Tenancy, RLS, auth, sessions, roles→scope | **80%** | Proved in CI, not only against Neon. Gaps: no login rate limit, no audit trail written |
| Preview audit (unauthenticated) | **90%** | Works end to end. Being retired in Phase 2 (`doc/11` Q1) and re-homed as the research engine |
| Domain verification (backend) | **70%** | DNS + file work. EMAIL method structurally dead; no transfer; no UI |
| Onboarding + invitations | **65%** | Wizard and API real. Delivery by copy-pasted URL |
| Documents / classification / indexing | **25%** | Broken against a real database (§4.1, §4.2). No classifier. No UI |
| Scoped retrieval layer (the security core) | **5%** | `scoped_connection` exists; no retrieval query of any kind |
| Company Brain + review gate | **0%** | Not started |
| Grounding + calculators | **8%** | One calculator, wired only to Preview |
| Dashboards / seven directors | **12%** | Shell + 67 offering specs as data. Zero widgets, zero numbers |

---

## 2. Phase status against `doc/12-IMPLEMENTATION-PLAN.md`

| Phase | State | Note |
|---|---|---|
| **P0 — CI and the remote** | **code complete — remote verification deferred** | Everything proved locally against the CI image. `gh` is not installed on this machine, so the green Actions run has to be confirmed by Parul. See §6 |
| P1 — Correctness | next | Fixes §4.1, §4.2, §4.6. Its migration `0010` collides in number with the Neon drift — see §5 |
| P2 — Retire the preview product | pending | |
| P3 — Identity | pending | |
| P4 — Security | pending | |
| P5–P9 — the onboarding spine | pending | |
| P10–P13 — the Brain | pending | |
| P14–P17 — product surface | pending | |
| P18–P21 — completion | pending | |

---

## 3. What Phase 0 built

**`.github/workflows/ci.yml`** — the api job now boots a `pgvector/pgvector:pg17`
service container, installs `psql`, runs `db/bootstrap.sql` with a generated
password masked out of the log, exports `NEXUS_DATABASE_URL` through
`$GITHUB_ENV`, and runs `alembic upgrade head → downgrade base → upgrade head`
before linting. `mypy` covers `app` and `tests`.

The image matters: the official `postgres` image has no `vector` extension, so
`db/bootstrap.sql` would fail on its first statement. So does the role — that
image makes `POSTGRES_USER` a superuser, and a superuser ignores every policy in
migration 0002 while the isolation suite passes.

**`requires_db` as a real marker** (`pyproject.toml`, `--strict-markers`),
replacing the `pytest.mark.skipif` alias that nine modules each kept their own
copy of. Five of those modules also called `pytest.skip()` inside a fixture;
those are now `assert DB_URL is not None`.

**One skip site and a guard** (`tests/conftest.py`).
`pytest_collection_modifyitems` is the only place a database test may be skipped.
`pytest_runtest_logreport` plus `pytest_sessionfinish` fail the session and name
every `requires_db` test that skipped, from any cause.

**`tests/test_ci_contract.py`** — six tests. A database is configured
(unconditional); it is reachable; the connected role has `rolsuper = false` and
`rolbypassrls = false`; `alembic_version` matches the migration head on disk;
`requires_db` is declared and markers are strict; and a skipped `requires_db`
test fails a run — proved by running a throwaway suite that contains one.

**`tests/dburl.py` resolves the URL once, at import.** It read the environment on
every call, and `conftest.py` pins `NEXUS_DATABASE_URL` to empty for hermeticity
— so a runtime read fell through to the `.env` fallback, which exists locally and
never in CI. The same code read Neon here and `None` there.

**Coverage with a floor** — `--cov-fail-under=74`, branch coverage, the measured
figure rounded down. A ratchet to make a deleted test visible, not a quality
claim.

**`scripts/db-ci.ps1`** — not on the phase's build list, and added because
without it there is no way to run the gate locally at all (§5). It builds a
throwaway database from the CI image and the repository's own `bootstrap.sql` and
migrations, on port 55432, and points the shell at it. It never writes `.env`.
`-RunGate` runs the gate straight afterwards.

Decisions recorded: **ADR 0013** (the suite refuses to run without a database),
**ADR 0014** (the local gate builds its own database from the CI image, and the
three WSL traps that cost a debugging cycle each).

### What Phase 0 proved, and how

| Claim | Evidence |
|---|---|
| The isolation suite executes | `pytest tests/test_tenant_isolation.py -v` → **12 passed**, zero skipped |
| The whole suite is green against a real database | `pytest -q` → **664 passed**, coverage 74.21% |
| Migrations reverse | `alembic downgrade base` then `upgrade head`, clean, on every `db-ci.ps1` run |
| Removing the RLS policy turns the build red | `workspace_isolation` commented out of migration 0002 → **3 passed, 9 errors, exit 1**, with `InsufficientPrivilege: new row violates row-level security policy for table "workspace"`. Restored; 664 passed again |
| No database turns the build red | An unconfigured URL → `test_a_database_is_configured` fails **and** the guard reports `94 requires_db test(s) were skipped`, exit 1 |
| The full gate is green | `.\scripts\ci.ps1` → parse, ruff check, ruff format, mypy strict, pytest, tsc, lint, build — all PASS, `CI GREEN`, exit 0 |

---

## 4. What is still broken

Unchanged by Phase 0, and this is the list Phase 1 exists to clear. None of it
was caught before because CI had no database and the one test covering the upload
path monkeypatches the write.

### 4.1 🔴 Every document upload fails at the chunk INSERT — `review_state` drift

`documents/classify.py` defines `ReviewState` as
`auto_approved · needs_review · human_approved · quarantined`. Migration 0007
constrains the column to
`('auto_approved','pending_review','approved','rejected')`. `routes/documents.py`
inserts the Python value directly, and `_withhold` returns `needs_review` — not
in the allowed set. Every chunk of every upload violates
`ck_chunk_review_state` and the transaction rolls back.

The review queue compounds it: both queue queries and the partial index
`ix_chunk_pending_review` filter on `'pending_review'`, which nothing writes.

**Note for Phase 1:** the Neon instance in `.env` already has the four-value SQL
vocabulary, so it would not reproduce half of this. The CI database does. See §5.

### 4.2 🔴 The supersede path raises a CheckViolation

`UPDATE document SET status = 'superseded'` against a `ck_document_status` that
permits only `('pending','parsing','parsed','indexed','failed','quarantined')`.
Any upload carrying `supersedes_id` fails.

**The Neon instance already permits `'superseded'`.** The repository does not.

### 4.3 🔴 A new customer cannot create a workspace through the web app

`POST /domains/{claim_id}/workspace` is the only path that inserts a workspace,
and there is no `apps/web/app/api/domains/` directory, no claim page, and no
client function. After registering and signing in, a real user has no workspace,
so `current_scope` answers 403, so every `CurrentScope` endpoint — onboarding,
dashboards, documents, invitations — is unreachable from the UI. The
authenticated product has no working entry point.

### 4.4 🔴 There is no classifier

`_classify_all` hardcodes `suggested_scope=L5_PERSONAL`, `confidence=0.0`,
`classifier_failed=True`. `classify_chunk` is the *gate* that decides whether to
believe a suggestion; nothing produces one. So 100% of content is withheld and
`chunks_indexed` is structurally always 0.

### 4.5 🔴 No email is ever sent

`FileMailer` is never instantiated. `send_verification` has zero callers.
Consequently `email_verified_at` can never be set, the EMAIL domain-verification
method is unreachable, and invitations are delivered by the inviter copy-pasting
a raw token URL.

### 4.6 🟠 Non-secure cookies and public API docs from one unset variable

`env` defaults to `local`, and `is_local` also returns true for `ci`. A missing
`NEXUS_ENV` in production therefore serves `/docs` and `/openapi.json` and sets
`secure=False` on both the session and CSRF cookies. The validator written to
prevent exactly this, `_required_in_deployed_envs`, has the body `return v`.

---

## 5. The developer database is five migrations ahead of the repository

Found by `test_the_schema_is_migrated_to_head` on its first run, and recorded as
**D23** in `DECISIONS-REQUIRED.md` §5c.

```
the database is at ['0014'] but the migrations on disk head at ['0009']
```

The Neon instance in `.env` also holds `company_brain`, `question` and
`question_choice` — no migration here creates them — and its `ck_document_status`
already permits `'superseded'`. Five migrations were applied to it from a working
tree that is in no commit, no branch, no stash and no other worktree; all four
were checked.

**Why it matters beyond tidiness.** A local run against that database proves
something other than what the repository contains, in both directions: a defect
the repo still has can pass (§4.2 is exactly that), and a fix the repo has made
can fail. Two of the 🔴 items above concern precisely the constraints that differ.
It also means Phase 1's migration `0010` collides by number with one already
applied there.

`scripts/db-ci.ps1` sidesteps it entirely — the gate no longer depends on Neon's
contents — but what to do with those five migrations is Parul's call.
**Nothing was reset.**

---

## 6. What needs Parul

| # | What | Blocks |
|---|---|---|
| **The Actions run** | Push, confirm CI is green on the remote, then confirm it goes red with `workspace_isolation` commented out of migration 0002. `gh` is not installed here, so this is the one part of Phase 0's acceptance test that could not be watched from this machine | Marking P0 complete rather than *code complete* |
| **D23** | Reset the Neon instance to the repository's head, reconstruct `0010`–`0014`, or accept it as scratch. Recommendation: reset — the three extra tables are empty | Trusting any local run; Phase 1's migration number |
| **D3** | Google API credentials | P18 (GA4, Search Console), Google sign-in |
| **D10** | Confirm Zoho as the CRM with the first design partner | P18, P19 |
| **D13** | Anthropic access and model tier per execution mode | P14, P20 |
| **`doc/11` §5.4** | The five business calls — B2, B3 and B5 shape the build | P16 onward |

Everything else `doc/11` settled. Nothing in Phase 1 is blocked.

---

## 7. Pending work list

Cleared in Phase 0: **C5** (Postgres in CI, fail on skip), **C6** (Alembic both
directions), **M9** (coverage, `--strict-markers`, type-check `tests/`).

### 🔴 Critical — blocks the application from being usable

| P | ID | Task | Phase | Current status | Dependencies | Effort |
|---|---|---|---|---|---|---|
| 🔴 | C1 | Reconcile `ReviewState` with `ck_chunk_review_state`; migration 0010 | P1 | §4.1 — every upload rolls back | D23 for the number | 0.5 d |
| 🔴 | C2 | Add `'superseded'` to `ck_document_status` | P1 | §4.2 — raises | C1 | 0.25 d |
| 🔴 | C7 | Replace the no-op secret validator with a startup refusal | P1 | `config.py` returns `v` | none | 0.5 d |
| 🔴 | C8 | Make `NEXUS_ENV` fail closed | P1 | §4.6 | C7 | 0.5 d |
| 🔴 | C12 | Database timeouts and a sized pool | P1 | None set at all | none | 0.5 d |
| 🔴 | H10 | Global exception handler preserving `x-request-id` | P1 | Absent | none | 0.5 d |
| 🔴 | C3 | Domain-claim UI + the three missing BFF proxies | P5 | §4.3 — no authed entry point exists | none | 3 d |
| 🔴 | C4 | End-to-end test of the real signup journey against Postgres | P9 | Does not exist | C1, C2, C3 | 2 d |
| 🔴 | C9 | Rate-limit `/auth/login` and `/auth/register`; argon2 off the event loop | P4 | Unbounded; ~40–80 ms sync CPU per attempt | D14 settled | 1.5 d |
| 🔴 | C10 | Wire email delivery | P3 | §4.5 | D4 settled — SMTP | 1.5 d |
| 🔴 | C11 | API and web container images + a runnable stack | P9 | No Dockerfile anywhere | none | 2 d |

### 🟠 High — required for a complete, production-ready application

| P | ID | Task | Phase | Current status | Dependencies | Effort |
|---|---|---|---|---|---|---|
| 🟠 | H1 | The scoped retrieval layer | P10 | 5% — `scoped_connection` only | C1, embeddings | 8 d |
| 🟠 | H2 | `/evals/permissions` as executable red-team specs, written before H1 | P10 | Absent | — | 3 d |
| 🟠 | H3 | A real classifier behind the gate | P12 | §4.4 — hardcoded failure | C1, D13 if model-backed | 4 d |
| 🟠 | H4 | Document upload + review-queue UI | P8 | Absent | C1, C3 | 4 d |
| 🟠 | H5 | Write the audit trail | P4 | `audit_log` is dead schema | none | 2 d |
| 🟠 | H7 | RLS on `domain_claim` | P4 | No policy, 12 SQL sites | C1 | 1 d |
| 🟠 | H8 | Frontend test harness — Vitest + Playwright | P9 | Zero tests, no framework | C11 | 3 d |
| 🟠 | H9 | Retire the three test mirrors | P1 | `expire_previews`, `check_and_increment`, `scoped_connection` all mirrored | C5 ✅ | 2 d |
| 🟠 | H11 | Privacy and Terms pages | P16 | Deliberately absent; signups are live | content | 1 d |
| 🟠 | H12 | Grounding pipeline + `generation` table | P14 | 8% — one calculator | H1, D13 | 8 d |
| 🟠 | H13 | Close the 14 open items in `AUDIT-FINDINGS.md` | P1, P4 | Open and scheduled | C9 for three | 3 d |
| 🟠 | H14 | Behavioural tests for the four untested modules | P1 | `routes/onboarding.py`, `auth/domains.py`, `domain/invitations.py`, `retrieval/scoped.py` | C5 ✅ | 3 d |
| 🟠 | H15 | Reconcile the landing page with what exists | P16 | 35 capabilities named as product | none | 0.5 d |
| 🟠 | H16 | Fix the skip link and the reduced-motion regression | P16 | Broken on 8 of 9 pages | none | 1 d |

**H6 (workspace switcher) is cancelled** — `doc/11` Q9 makes it one person, one
company. ~2 days saved.

### 🟡 Medium — important, not blocking

| P | ID | Task | Phase | Dependencies | Effort |
|---|---|---|---|---|---|
| 🟡 | M1 | Dashboard shell + first real widgets | P15, P16 | H1, H12, D7 ✅, D8 ✅ | 12 d |
| 🟡 | M3 | Domain claim lifecycle — recheck job, ownership transfer, revocation | P3 | none | 2 d |
| 🟡 | M4 | Document list + signed download | P8 | H4 | 1.5 d |
| 🟡 | M5 | Persona: use it or drop it | P4 | none | 1 d |
| 🟡 | M6 | Alembic drift detection — every CHECK constraint against the enum that feeds it | P1 | C5 ✅ | 1 d |
| 🟡 | M7 | Config hygiene — seven dead settings, `.env.example` drift | P1 | C7 | 0.5 d |
| 🟡 | M8 | One scoping primitive — route the five implementations through `retrieval/scoped.py` | P10 | H1 | 1 d |
| 🟡 | M10 | Validate API responses at the web boundary — four blind `as` casts | P5 | none | 1 d |
| 🟡 | M11 | `auth-proxy` hardening | P4 | C9 | 0.5 d |
| 🟡 | M12 | Real state handling in `TeamStep` | P17 | none | 0.5 d |
| 🟡 | M13 | `loading.tsx` / `global-error.tsx` | P16 | none | 0.5 d |
| 🟡 | M14 | Reconcile the scoreable count — data says five, copy says six | P15 | D8 ✅ | 0.5 d |
| 🟡 | M15 | Move the embedding pass out of the API process | P9 | C11 | 1.5 d |

**M2 (preview deletion path) is void** — `doc/11` D9: no preview data is retained
once P2 retires the product, so there is nothing to expire or delete.

### 🟢 Low — polish

| P | ID | Task | Effort |
|---|---|---|---|
| 🟢 | L1 | Delete the ten dead functions and components, or add the callers they were built for | 0.5 d |
| 🟢 | L2 | Drop or use the dead columns `chunk.is_dept_aggregate`, `document.retention_until`, `audit_log.impersonated_user_id` | 0.5 d |
| 🟢 | L3 | Make `WidgetState.WARMING` / `SELF_REPORTED` reachable, or remove them from both layers | 0.25 d |
| 🟢 | L4 | Link or remove the four orphaned landing sections | 0.25 d |
| 🟢 | L5 | Assert `config.embedding_dim` equals the migration's `EMBEDDING_DIM` | 0.1 d |
| 🟢 | L6 | Use the `pgvector` SQLAlchemy type instead of the string literal in `embed.py` | 0.25 d |
| 🟢 | L8 | Unused component props — use or remove | 0.25 d |

**L7 is done** — the untracked planning documents in `doc/` are committed.

---

## 8. The gate

```powershell
.\scripts\db-ci.ps1 -RunGate
.\scripts\db-ci.ps1
.\scripts\ci.ps1
.\scripts\db-ci.ps1 -Action down
```

`ci.ps1` runs: scripts parse · ruff check · ruff format · mypy strict over `app`
and `tests` · pytest with the coverage floor · tsc · next lint · next build.

**It needs a database.** Without one, `test_a_database_is_configured` fails and
the skip guard names every database test that did not run. That is deliberate —
see ADR 0013.

**Stop the web dev server first.** Both it and `next build` write
`apps\web\.next`.

---

## 9. Next

**Phase 1 — Correctness.** Migration 0010 (`review_state` reconciliation,
`'superseded'`), a real config validator, cookie security independent of `ci`,
database timeouts, a global exception handler preserving `x-request-id`, and a CI
test comparing every `CHECK` constraint against the Python enum that feeds it —
the exact class of §4.1 and §4.2.

**Answer D23 first.** Phase 1's migration is numbered `0010`, and so is one of
the five already applied to the Neon instance.
