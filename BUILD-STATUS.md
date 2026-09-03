# NEXUS OS — Build Status

**Regenerated:** 3 September 2026, at the end of **Phase 1** of
`doc/12-IMPLEMENTATION-PLAN.md`.
**Method:** every claim below was run, not read. Where a figure is quoted, the
command that produced it is named.

---

## 1. Where this stands

**~34% of the product.** Phase 0 and Phase 1 between them added no product
surface, deliberately. What they changed is whether the rest can be trusted:
Phase 0 made the suite capable of proving something, and Phase 1 used it to make
the claims already in the repository true.

| | Before Phase 0 | Now |
|---|---|---|
| Database tests in CI | **94 skipped, exit 0** | 714 executed, exit 0 |
| Row-level security proved automatically | no | yes — 12 isolation tests, executed |
| Migrations ever run in reverse | no | yes, every run: `upgrade → downgrade base → upgrade` |
| `mypy --strict` over `tests/` | no | yes, 107 files clean |
| Coverage measured | no | 75.86% branch, with a floor that only rises |
| A skipped database test | invisible | fails the build, by name |
| Document upload against Postgres | **rolled back, every time** | writes, and reaches the review queue |
| Superseding a document | **raised** | retires the earlier row |
| A deployed env with no secrets | booted | refuses to start, naming the variable |
| A missing `NEXUS_ENV` | insecure cookies, public `/docs` | refuses to start |
| An unhandled exception | uncorrelatable 500 | carries the `x-request-id` in the log |
| Database timeouts | none set | four, asserted with `SHOW` |

Two of the three 🔴 defects are cleared. The engineering foundation is now
genuinely strong, and almost none of the product is still reachable by a user —
that split is unchanged, and Phase 5 is where it starts to close.

| Area | Complete | Basis |
|---|---|---|
| Foundation — repo, config, logging, health, CI, migrations | **100%** | Real Postgres in CI both directions; config fails closed; four DB timeouts; correlated 500s. Nothing outstanding |
| Tenancy, RLS, auth, sessions, roles→scope | **82%** | Proved in CI. Cookies now `Secure` outside local. Gaps: no login rate limit, no audit trail written |
| Preview audit (unauthenticated) | **90%** | Works end to end. Being retired in Phase 2 (`doc/11` Q1) and re-homed as the research engine |
| Domain verification (backend) | **70%** | DNS + file work. EMAIL method structurally dead; no transfer; no UI |
| Onboarding + invitations | **65%** | Wizard and API real. Delivery by copy-pasted URL |
| Documents / classification / indexing | **45%** | Upload, chunking, withholding and the review queue all work against Postgres. Gaps: no classifier, no UI |
| Scoped retrieval layer (the security core) | **5%** | `scoped_connection` exists; no retrieval query of any kind |
| Company Brain + review gate | **0%** | Not started |
| Grounding + calculators | **8%** | One calculator, wired only to Preview |
| Dashboards / seven directors | **12%** | Shell + 67 offering specs as data. Zero widgets, zero numbers |

---

## 2. Phase status against `doc/12-IMPLEMENTATION-PLAN.md`

| Phase | State | Note |
|---|---|---|
| **P0 — CI and the remote** | ✅ **complete** | Confirmed green on the remote, with `test_tenant_isolation.py`'s 12 tests **executed**. One sub-step — watching CI go red with the RLS policy removed — was exercised locally rather than on the remote |
| **P1 — Correctness** | ✅ **complete** | Migration 0010, a real config validator, four database timeouts, a correlated exception handler, and a constraint-versus-enum test. Every acceptance criterion proved locally; see §3 |
| P2 — Retire the preview product | next | Deletes `preview.py`, the hero URL form, `client-address.ts`, three test modules and the `preview_session` table. `test_constraint_enum_parity.py` will fail until its `UNMAPPED` entry for `ck_preview_session_status` goes with the table — deliberately |
| P3 — Identity | pending | |
| P4 — Security | pending | |
| P5–P9 — the onboarding spine | pending | |
| P10–P13 — the Brain | pending | |
| P14–P17 — product surface | pending | |
| P18–P21 — completion | pending | |

---

## 3. What Phase 1 built

**Migration 0010, and two enums that did not exist.** The two check constraints
no code path could satisfy are the reason this phase exists.

`ck_chunk_review_state` permitted `auto_approved · pending_review · approved ·
rejected`; `ReviewState` produced `auto_approved · needs_review ·
human_approved · quarantined`. One value of four overlapped, and since
`_classify_all` always withholds — there is no classifier yet, which is I4
working as intended — **every chunk of every upload rolled the transaction
back**. The SQL vocabulary won, because three things already depended on it, so
the migration changes no SQL here and the enum moved instead.

`ck_document_status` is changed: `'superseded'` was written by the supersede
path and permitted by nothing. `'parsing'` and `'parsed'` were removed at the
same time — nothing has ever written them, and a constraint wider than the code
is vocabulary a later reader takes for a supported state.

`app/documents/status.py` is the point rather than a detail. That constraint had
**no** Python counterpart, so there was nowhere for the mistake to be visible.
`review_state_code()` is the same idea for the other one: a named write path, so
no call site reaches for `.value` or a literal of its own.

**Configuration that fails closed** (ADR 0015). `_required_in_deployed_envs` was
a validator with the body `return v` — it enforced nothing while presenting as a
security control. `env` defaulted to `local` and `is_local` answered true for
`ci`, so a deployment that forgot `NEXUS_ENV` served `/docs` publicly and set
`secure=False` on both cookies. Now: `NEXUS_ENV` is required with no default,
the validator is real and names every missing secret at once, `is_local` splits
into `cookies_secure` and `docs_enabled`, and `session_secret` — declared,
documented, pinned, and read by no line of code — is deleted.

**Four database timeouts**, none redundant, asserted with `SHOW` against the
application's own engine. And the pooler switch becomes explicit configuration
rather than `"-pooler" in url`.

**A correlated 500.** There was no exception handler at all. The response now
carries the request id and nothing else — not the exception type, not its
message, not a traceback.

**A test for the class, not the instances.** `test_constraint_enum_parity.py`
requires every value-list `CHECK` to equal its enum in *both* directions, and
requires every such constraint to be registered, so a new one added without a
mapping fails the build.

### What Phase 1 proved, and how

| Claim | Evidence |
|---|---|
| **A document uploads end to end against Postgres** | `POST /documents` with `_record` and the object store unpatched, authenticated by a real session cookie against a real `user_session` row. Chunks land at `review_state = 'pending_review'`, scope `L5`, owner the uploader |
| **They appear in the review queue** | `GET /documents/review-queue` returns them — a queue that was previously unfillable, because index and query both filtered a value nothing could write |
| **Superseding retires the earlier document** | The old row reaches `'superseded'`; the replacement stays `'indexed'` |
| **A deployed env without its secret refuses to start** | `NEXUS_ENV=production` with an empty `NEXUS_STORAGE_SIGNING_SECRET` → `import app.main` exits **1**, naming the variable |
| **An unhandled exception is correlatable** | The 500 body carries `request_id`, the `x-request-id` header matches, and the emitted log line carries the same value with the traceback. No customer content in the body |
| **The timeouts are live on the server** | `SHOW statement_timeout` → `15s`, `lock_timeout` → `5s`, `idle_in_transaction_session_timeout` → `30s`; an overrunning statement is cancelled |
| The suite is green | **714 passed**, coverage 75.86% against a floor of 75 |
| The full gate is green | `.\scripts\ci.ps1` → `CI GREEN`, exit 0 |
| The app still boots | `/health` 200, `/health/ready` 200 with `database: ok`, `/docs` **404 in `ci`** |

**Proved it can fail.** With `'superseded'` removed from migration 0010 the
behavioural test went red *and* the parity test named the discrepancy exactly —
`Only in Python: ['superseded']`. That is the class-level guard doing its job:
it would catch the next such drift before anyone exercised the path. Restored;
714 passed.

### Three things the tests found that the plan did not anticipate

- **The transaction-pooler branch in `app/db.py` had never worked.**
  `prepared_statement_cache_size` was passed to `create_async_engine`, which
  rejects it — SQLAlchemy's asyncpg adapter pops it from the *connect* keywords
  — so the engine raised `TypeError` before it could connect. Nothing in the
  suite used a pooler URL and production connects to Neon's direct host, so it
  had never once been executed.
- **The request id could not reach the exception handler.** When `call_next`
  raises, the middleware's `finally` resets the `ContextVar` before
  `ServerErrorMiddleware` — which sits *outside* it — invokes the handler, and
  the line setting the response header is never reached. The id now travels on
  the ASGI scope, which both share.
- **The process never closed its connection pool.** Now disposed in `lifespan`
  shutdown. In a test this was worse than untidy: transports created on the
  app's loop were collected on a closed one, and `filterwarnings = ["error"]`
  turned the unraisable exception into a failure of whichever test ran next.

---

## 4. What is still broken

Three of the six are cleared by Phase 1. The three that remain are all *absent
features* rather than broken ones — nothing here fails at runtime; it simply
does not exist yet, and each has a phase.

### 4.1 ✅ ~~Every document upload fails at the chunk INSERT~~ — fixed

`ReviewState` now carries the column's own vocabulary, `review_state_code()` is
the single write path, and `test_constraint_enum_parity.py` asserts the two are
set-equal in both directions on every run. Proved by an upload reaching Postgres
and appearing in the review queue.

### 4.2 ✅ ~~The supersede path raises a CheckViolation~~ — fixed

Migration 0010 permits `'superseded'` and retires `'parsing'`/`'parsed'`, which
nothing had ever written. `DocumentStatus` is the enum the constraint had never
had. Proved by superseding a document and reading the earlier row's status back.

### 4.3 🔴 A new customer cannot create a workspace through the web app

**Phase 5.** `POST /domains/{claim_id}/workspace` is the only path that inserts
a workspace, and there is no `apps/web/app/api/domains/` directory, no claim
page, and no client function. After registering and signing in, a real user has
no workspace, so `current_scope` answers 403, so every `CurrentScope` endpoint —
onboarding, dashboards, documents, invitations — is unreachable from the UI. The
authenticated product still has no working entry point, and this is now the
largest single thing standing between the code and a user.

### 4.4 🔴 There is no classifier

**Phase 12.** `_classify_all` hardcodes `suggested_scope=L5_PERSONAL`,
`confidence=0.0`, `classifier_failed=True`. `classify_chunk` is the *gate* that
decides whether to believe a suggestion; nothing produces one. So 100% of
content is withheld and `chunks_indexed` is structurally always 0.

Worth being precise now that the path works: this is I4 behaving correctly, not
a bug. Every upload lands in the review queue because the absence of a
classifier is a reason to deny, and the review queue is where a human decides.
What is missing is the suggestion, not the gate.

### 4.5 🔴 No email is ever sent

**Phase 3.** `FileMailer` is never instantiated and `send_verification` has zero
callers. Consequently `email_verified_at` can never be set, the EMAIL
domain-verification method is unreachable, and invitations are delivered by the
inviter copy-pasting a raw token URL. `doc/11` settled the transport (SMTP), so
nothing blocks it.

### 4.6 ✅ ~~Non-secure cookies and public API docs from one unset variable~~ — fixed

`NEXUS_ENV` is required, the validator refuses to boot without the secrets a
deployed environment needs, and `is_local` is replaced by `cookies_secure` and
`docs_enabled`, which differ on `ci`. ADR 0015.

---

## 5. The developer database was five migrations ahead — D23, resolved

Found by `test_the_schema_is_migrated_to_head` on its first run:

```
the database is at ['0014'] but the migrations on disk head at ['0009']
```

The Neon instance in `.env` also held `company_brain`, `question` and
`question_choice` — no migration here creates them — and a `ck_document_status`
that already permitted `'superseded'`. Five migrations had been applied to it
from a working tree that is in no commit, no branch, no stash and no worktree;
all four were checked.

**Why it mattered beyond tidiness.** A run against that database proved something
other than what the repository contains, in both directions: a defect the repo
still has could pass — §4.2 is exactly that case — and a fix the repo had made
could fail.

**Resolved on Parul's instruction: the database was reset to the repository's
head.** Its schema was recorded first, in
`doc/archive/neon-schema-before-the-d23-reset.md`, because the work is not
throwaway — `company_brain` is Phase 13's central table and
`question`/`question_choice` are Phase 7's catalogue. `pg_dump` could not be used
(client 17.11, server 18.4), so both schemas were introspected and diffed
structurally. 241 rows went with it: 68 `app_user`, 93 `user_session`, 48
`tenant`, 17 `domain_claim`, 14 `preview_session`, and **no `workspace` or
`membership` row at all** — walkthrough residue, nothing that had ever completed
registration.

Verified after: columns, indexes, policies and row-security flags are identical
to a database built from `bootstrap.sql` and migrations 0001–0009, as are all 65
constraints once the `NOT NULL` rows Postgres 18 exposes and 17 does not are set
aside. The full suite runs green against Neon.

**Two consequences for Phase 1.** Migration numbers `0010`–`0014` are free, so
its migration is `0010` as `doc/12` assumes. And the drift was masking three
findings that are real again: **C1** never differed between the two databases and
is still broken against the Python enum; **C2** is missing once more; and **M5**
— somebody had chosen *use the persona table* and added three columns, which is a
decision for Parul rather than an inheritance.

Still open and not answerable from here: whether application code was lost with
those five migrations. Nothing in `app/` references the three tables, so if there
was code, it went with the tree.

---

## 6. What needs Parul

| # | What | Blocks |
|---|---|---|
| ~~**The Actions run**~~ | ✅ Confirmed green, 12 isolation tests executed. The red run remains optional and unwitnessed on the remote — see §3 | — |
| ~~**D23**~~ | ✅ Answered and done — Neon reset to the repository's head, schema recorded first in `doc/archive/` | — |
| **D3** | Google API credentials | P18 (GA4, Search Console), Google sign-in |
| **D10** | Confirm Zoho as the CRM with the first design partner | P18, P19 |
| **D13** | Anthropic access and model tier per execution mode | P14, P20 |
| **`doc/11` §5.4** | The five business calls — B2, B3 and B5 shape the build | P16 onward |

Everything else `doc/11` settled. Nothing in Phase 1 is blocked.

---

## 7. Pending work list

Cleared in Phase 0: **C5** (Postgres in CI, fail on skip), **C6** (Alembic both
directions), **M9** (coverage, `--strict-markers`, type-check `tests/`).

Cleared in Phase 1: **C1** (`review_state`), **C2** (`'superseded'`), **C7** (the
no-op validator), **C8** (`NEXUS_ENV` fails closed), **C12** (database
timeouts), **H10** (correlated exception handler), and **M6** (constraint drift
detection, as `test_constraint_enum_parity.py`).

**Nothing critical remains that fails at runtime.** Every 🔴 below is a feature
that does not exist yet.

### 🔴 Critical — blocks the application from being usable

| P | ID | Task | Phase | Current status | Dependencies | Effort |
|---|---|---|---|---|---|---|
| 🔴 | C3 | Domain-claim UI + the three missing BFF proxies | P5 | §4.3 — no authed entry point exists | none | 3 d |
| 🔴 | C4 | End-to-end test of the real signup journey against Postgres | P9 | Does not exist | C1, C2, C3 | 2 d |
| 🔴 | C9 | Rate-limit `/auth/login` and `/auth/register`; argon2 off the event loop | P4 | Unbounded; ~40–80 ms sync CPU per attempt | D14 settled | 1.5 d |
| 🔴 | C10 | Wire email delivery | P3 | §4.5 | D4 settled — SMTP | 1.5 d |
| 🔴 | C11 | API and web container images + a runnable stack | P9 | No Dockerfile anywhere | none | 2 d |

### 🟠 High — required for a complete, production-ready application

| P | ID | Task | Phase | Current status | Dependencies | Effort |
|---|---|---|---|---|---|---|
| 🟠 | H1 | The scoped retrieval layer | P10 | 5% — `scoped_connection` only | embeddings | 8 d |
| 🟠 | H2 | `/evals/permissions` as executable red-team specs, written before H1 | P10 | Absent | — | 3 d |
| 🟠 | H3 | A real classifier behind the gate | P12 | §4.4 — hardcoded failure. The gate and the queue now work, so this is the missing *suggestion*, not the missing guarantee | D13 if model-backed | 4 d |
| 🟠 | H4 | Document upload + review-queue UI | P8 | Absent. The API behind it now works end to end | C3 | 4 d |
| 🟠 | H5 | Write the audit trail | P4 | `audit_log` is dead schema | none | 2 d |
| 🟠 | H7 | RLS on `domain_claim` | P4 | No policy, 12 SQL sites | none | 1 d |
| 🟠 | H8 | Frontend test harness — Vitest + Playwright | P9 | Zero tests, no framework | C11 | 3 d |
| 🟠 | H9 | Retire the three test mirrors | P2 | `expire_previews`, `check_and_increment`, `scoped_connection` all mirrored. Two of the three die with the preview product | C5 ✅ | 2 d |
| 🟠 | H11 | Privacy and Terms pages | P16 | Deliberately absent; signups are live | content | 1 d |
| 🟠 | H12 | Grounding pipeline + `generation` table | P14 | 8% — one calculator | H1, D13 | 8 d |
| 🟠 | H13 | Close the 14 open items in `AUDIT-FINDINGS.md` | P4 | Open and scheduled | C9 for three | 3 d |
| 🟠 | H14 | Behavioural tests for the four untested modules | P3, P5 | `routes/onboarding.py`, `auth/domains.py`, `domain/invitations.py`, `retrieval/scoped.py`. `test_document_upload_db.py` is the pattern to copy | C5 ✅ | 3 d |
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
| 🟡 | M5 | Persona: use it or drop it. The lost migrations had chosen *use it* — three columns and a check, recorded in `doc/archive/neon-schema-before-the-d23-reset.md` §3 | P4 | none | 1 d |
| 🟡 | ~~M6~~ | ✅ **Done** — `test_constraint_enum_parity.py`, and it requires every value-list constraint to be registered, not only the ones somebody remembered | P1 | — | — |
| 🟡 | M7 | Config hygiene — `session_secret` deleted and `.env.example` drift now fails the build; four settings (`signed_url_ttl_seconds`, `mailer_backend`, `mail_root`, `model_cache_dir`) are still unread and deliberately kept until P3 wires email | P3 | C10 | 0.25 d |
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

**It needs `NEXUS_ENV` too**, since Phase 1. `.env` supplies it locally and the
workflow sets it in CI; a missing one is now a startup error rather than a
silent `local` (ADR 0015).

**Stop the web dev server first.** Both it and `next build` write
`apps\web\.next`.

---

## 9. Next

**Phase 2 — Retire the preview product.** Per `doc/11` Q1 the unauthenticated
audit is removed and its engine re-homed as the research engine. Deletes
`app/routes/preview.py`, the hero URL form, `lib/client-address.ts`, three test
modules and — in migration 0011 — the `preview_session` table. The SSRF guard
with its 89 test cases, the pinned crawler, the extractor and the scoring
calculators all survive and move behind authentication.

Two things Phase 1 leaves for it deliberately:

- `test_constraint_enum_parity.py` carries an `UNMAPPED` entry for
  `ck_preview_session_status` saying the table is dropped in Phase 2. When it is,
  `test_no_unmapped_entry_outlives_its_constraint` fails until the entry goes.
  That is the design: an exemption list nobody prunes becomes a list of things
  nobody checks.
- **H9**, the three test mirrors. Two of the three — `expire_previews` and
  `check_and_increment` — die with the preview product, so the cheapest moment
  to retire them is while the code around them is being deleted anyway.

Nothing blocks it.
