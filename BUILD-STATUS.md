# NEXUS OS — Build Status

**Regenerated:** 3 September 2026, at the end of **Phase 2** of
`doc/12-IMPLEMENTATION-PLAN.md`.
**Method:** every claim below was run, not read. Where a figure is quoted, the
command that produced it is named.

---

## 1. Where this stands

**~33% of the product.** Three phases in, and the percentage has gone *down*.
That is the honest reading and not a rounding artefact: Phase 2 deleted a
feature that worked. Phase 0 made the suite capable of proving something, Phase 1
used it to make the repository's existing claims true, and Phase 2 removed the
one thing a stranger could use — because what they could use it for was an
analysis of a company they do not own.

| | Before Phase 0 | Now |
|---|---|---|
| Database tests in CI | **94 skipped, exit 0** | 667 executed, exit 0 — and **actually executed**: until Phase 2 the pytest step never ran at all, see §3 |
| Row-level security proved automatically | no | yes — 12 isolation tests, executed |
| Migrations ever run in reverse | no | yes, every run: `upgrade → downgrade base → upgrade` |
| `mypy --strict` over `tests/` | no | yes, 105 files clean — and passing on a *clean runner*, which it had not been doing |
| Coverage measured | no | 76.43% branch in CI, with a floor that only rises |
| A skipped database test | invisible | fails the build, by name |
| Document upload against Postgres | **rolled back, every time** | writes, and reaches the review queue |
| Superseding a document | **raised** | retires the earlier row |
| A deployed env with no secrets | booted | refuses to start, naming the variable |
| A missing `NEXUS_ENV` | insecure cookies, public `/docs` | refuses to start |
| An unhandled exception | uncorrelatable 500 | carries the `x-request-id` in the log |
| Database timeouts | none set | four, and proved live **on Neon** as well as in CI — §4.7 |
| A server-side fetch without a session | `POST /preview`, open to anyone | none, and an import-graph test fails the build if one returns |
| Data held about a company with no account | retained under a TTL and a sweep | **not collected** — D9 void |

Two of the three 🔴 defects are cleared. The engineering foundation is now
genuinely strong, and almost none of the product is still reachable by a user —
that split is unchanged, and Phase 5 is where it starts to close.

| Area | Complete | Basis |
|---|---|---|
| Foundation — repo, config, logging, health, CI, migrations | **100%** | Real Postgres in CI both directions; config fails closed; correlated 500s; four database timeouts, live on Neon as well as CI. Briefly 95% — §4.7 was open between its discovery and its fix |
| Tenancy, RLS, auth, sessions, roles→scope | **82%** | Proved in CI. Cookies now `Secure` outside local. Gaps: no login rate limit, no audit trail written |
| ~~Preview audit (unauthenticated)~~ | **retired** | Deleted in Phase 2 (`doc/11` Q1). The entry point is gone; the engine moved to `app/research/` |
| Research engine (`app/research/`) | **35%** | Guard, single-page crawler and extractor, all behind authentication and all passing from the new location. No job model, no multi-page crawl, no callers — P11 |
| Domain verification (backend) | **70%** | DNS + file work. EMAIL method structurally dead; no transfer; no UI |
| Onboarding + invitations | **65%** | Wizard and API real. Delivery by copy-pasted URL |
| Documents / classification / indexing | **45%** | Upload, chunking, withholding and the review queue all work against Postgres. Gaps: no classifier, no UI |
| Scoped retrieval layer (the security core) | **5%** | `scoped_connection` exists; no retrieval query of any kind |
| Company Brain + review gate | **0%** | Not started |
| Grounding + calculators | **8%** | One calculator, and since Phase 2 it is wired to nothing. It survives because P11 needs it — `doc/11` §3.1 calls its scores the dashboard's first real numbers |
| Dashboards / seven directors | **12%** | Shell + 67 offering specs as data. Zero widgets, zero numbers |

---

## 2. Phase status against `doc/12-IMPLEMENTATION-PLAN.md`

| Phase | State | Note |
|---|---|---|
| **P0 — CI and the remote** | ✅ complete, with one claim withdrawn | The workflow, the Postgres service and the skip guard are all real and all working. But **"confirmed green on the remote" was wrong**: the run it referred to was red, and every run since has been, because `mypy` failed on an undeclared `bs4` before pytest was reached. The isolation tests were confirmed executed *locally*. They first ran on a remote runner in Phase 2 |
| **P1 — Correctness** | ✅ **complete** | Migration 0010, a real config validator, a correlated exception handler and a constraint-versus-enum test. The fourth item — four database timeouts — was correct in code and green in CI while doing nothing on Neon; that gap (finding #15) is closed, so the phase's claims now all hold where it matters |
| **P2 — Retire the preview product** | ✅ **complete, green in CI** | Run [33730363386](https://github.com/xi-4206pbhoite/nexus-os/actions/runs/33730363386) — 667 passed, migrations both directions, coverage 76.43%. `POST /preview`, the hero URL form, both components, the BFF proxy, `client-address.ts`, three test modules and the `preview_session` table are gone. The guard, crawler and extractor moved to `app/research/`; the rate limiter is re-keyed to `(workspace, global)`. See §3 |
| P3 — Identity | next | Email that actually sends, password reset, one person to one company. Blocked on nothing — `doc/11` settled SMTP |
| P4 — Security | pending | |
| P5–P9 — the onboarding spine | pending | |
| P10–P13 — the Brain | pending | |
| P14–P17 — product surface | pending | |
| P18–P21 — completion | pending | |

---

## 3. What Phase 2 built

Nothing. That is the phase.

**`POST /preview` is gone**, and with it the only endpoint in the product that
performed a server-side fetch for a caller who had not identified themselves.
The reason is the one its own docstring gave: *"anyone can type a competitor's
URL, and without that limit NEXUS would crawl a company the requester does not
own, name its competitors, and hand that to a stranger — a competitive-
intelligence product sold by accident."* The docstring was right and the mitigation
— a reduced audit — was the wrong shape of answer. `doc/11` Q1 gave the right one.

Deleted: the route (339 lines), `apps/web/app/api/preview/route.ts`,
`PreviewForm.tsx`, `PreviewResult.tsx`, `lib/client-address.ts` and the whole
`X-Forwarded-For` trust chain, the hero URL form, `preview_ttl_hours`,
`trusted_proxy_ips`, `expire_previews`, `delete_previews_for_domain`, three test
modules, and — in migration 0011 — the `preview_session` table.

**The engine moved rather than died.** `ssrf.py`, `crawler.py` and `extract.py`
are now `app/research/`, and the package docstring says what the directory is
for. `app/calculators/audit.py` deliberately stayed where it is: it scores what
the extractor finds, and I1 keeps every calculation in one place.

**`test_no_unauthenticated_crawl.py` is the part that outlives the phase.**
Deleting a route removes today's exposure; nothing about the deletion stops the
next one being added. So the invariant is asserted structurally: an `ast` walk
over `app/`, from every route that declares no session dependency, failing if any
of them can reach `app.research.crawler` or `app.research.extract` at any depth.
It replaces `test_preview_scope.py`, which could only ever describe the one
endpoint it was written for.

Two details in it were not obvious and are worth carrying:

- **The walk is over the source, not `sys.modules`.** A runtime check sees only
  what the test session happened to import, and would go quiet exactly when a new
  import path appeared.
- **`app.research.ssrf` is exempted, narrowly.** It is the guard, not the fetch,
  and `connectors/domain_check.py` — which proves a domain claim by fetching a
  well-known file — has to use it. Forbidding it would push that path towards its
  own copy of the SSRF guard, which is the worst available outcome.

**The rate limiter is re-keyed**, `(ip, domain, global)` → `(workspace, global)`.
The first two limits lost their subject: there is no address to attribute a crawl
to when every caller is authenticated, and no reflected-DoS shape when the target
must be a claimed domain. No migration was needed — a bucket is an opaque string,
so the old rows are simply never written again and age out through
`purge_expired`. **The per-workspace number is a placeholder with a stated
reason:** P11 builds the research job model and will know what a run costs.

### What Phase 2 proved, and how

| Claim | Evidence |
|---|---|
| **Nothing answers at `/preview`** | `TestClient(create_app())` — `GET` and `POST` both **404**. Asserted through the app, so re-registering the router in `main.py` fails the build |
| **No anonymous route can reach the crawler** | `test_no_anonymous_route_can_reach_the_crawler`. It found `app.routes.preview` while the route still existed, and went green when it was deleted |
| **The guard suite passes unedited from its new home** | `tests/test_ssrf_guard.py` — **89 cases**. The diff against `dev` is three import lines. No assertion changed |
| **The calculator suite too** | `tests/test_audit_calculators.py` — 29 cases, one import line changed |
| **The redirect suite too** | `tests/test_crawler_redirects.py` — 18 cases, two import lines |
| **The exemption list pruned itself** | Removing `ck_preview_session_status` from `UNMAPPED` made `test_every_value_list_constraint_is_registered` fail against a database that still has the table — which is the tripwire Phase 1 built, firing on schedule |
| **The landing page has no URL field and builds** | `npx tsc --noEmit` clean, `npx next lint` clean, `npx next build` succeeds with no `/api/preview` route in the manifest |
| The suite is green **in CI** | **667 passed in 25s**, coverage **76.43%** against a floor of 75 — up from 75.86%, because the deleted code took its own uncovered branches with it. No `requires_db` test skipped, or `conftest.py` would have failed the session |
| **Migration 0011 runs both directions on a clean Postgres** | The workflow's `upgrade head → downgrade base → upgrade head`, with `Running upgrade 0010 -> 0011` and `Running downgrade 0011 -> 0010` both in the log |

**CI was red before this phase started, for two reasons, and neither was
visible.**

The first: `app/.../extract.py` imports `bs4` and **`beautifulsoup4` appeared in
no dependency list**. On a clean runner `pip install -e ".[dev]"` did not install
it, so `mypy` failed with *"cannot find implementation or library stub for module
named bs4"* — and mypy runs before pytest, so **the test step never executed on
any run since that file was written**, including the one that closed Phase 1. It
passed on the developer's machine because another package pulled `bs4` in
transitively.

The second was underneath it, and only appeared once the first was fixed:
`starlette` 1.6.0's `TestClient` imports `anyio.abc.BlockingPortal`, which `anyio`
4.15.0 deprecated. `filterwarnings = ["error"]` turned that into **nine
collection errors** — every module that builds a `TestClient`. Neither package is
ours. A narrow `ignore` naming the message, so a different `DeprecationWarning`
still fails the build.

Both are the same class of defect: **an unpinned dependency set means CI resolves
a different environment than the developer, and the difference is only visible on
the run.** The workflow has no lockfile, so this will recur.

**Locally, against Neon, four tests still fail — and that is the database, not
the code.** The developer's instance is at migration `0009`; head is `0011`, so
Phase 1's `0010` and Phase 2's `0011` are both unapplied. `alembic upgrade head`
clears all four. CI, on a clean Postgres migrated both directions, is **green**.

Three more failed here until §4.7 was fixed in this phase.

### What the tests found that the plan did not anticipate

- **`onboarding.py` authenticates in its body, not in its signature.** Three of
  its four routes call a local `_require_user(nexus_session)` instead of
  depending on `CurrentSession`, so they are authenticated in fact and *anonymous
  to any structural check*. The new test treats them as anonymous rather than
  arguing the point — a check that cannot see an authentication decision cannot
  rely on it — and the fix is to declare the dependency. **P5 owns those routes.**
- **`domain_check.check_well_known_file` is a second server-side fetch**, on
  `/domains/{claim_id}/check`, which is one of those routes. It is far narrower
  than the preview was — SSRF-guarded, address-pinned, no redirects, and tied to
  a claim the caller initiated — and the plan knowingly keeps it (`doc/12` §Phase
  2 says findings #3–#5 survive *because* `domain_check.py` does). But it is now
  the **only** unmetered outbound fetch in the product, and the per-domain bucket
  that finding #4 cited as mitigation was deleted by this phase. Finding #4 is
  updated to say so.
- **`FastAPI.include_router` no longer flattens.** In this version an included
  router appears in `app.routes` as one object holding its own routes, so a flat
  pass sees three documentation endpoints and nothing else. The first version of
  the import-graph test classified *every* route as authenticated and passed
  vacuously. The guard test written alongside it — "some routes are anonymous or
  this test proves nothing" — is what caught that, on the first run.

---

## 4. What is still broken

Four of the seven are cleared. The three that remain are all *absent features*
rather than broken ones — nothing here fails at runtime; it simply does not exist
yet, and each has a phase. §4.7 was both found and fixed inside Phase 2: it
failed silently, in production only, where CI could not see it.

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

### 4.7 ✅ ~~Three of the four database timeouts do not exist in production~~ — fixed

**Found in Phase 2, and it is a Phase 1 claim being withdrawn.** `app/db.py`
passes `statement_timeout`, `lock_timeout` and
`idle_in_transaction_session_timeout` in asyncpg's `server_settings`. Against
Neon, `SHOW` returns `0`, `0` and `5min` — the defaults. `application_name`, sent
in the same dictionary, arrives intact, so the connection is healthy and Neon's
proxy is filtering the startup packet to an allowlist.

The code is right, `tests/test_db_timeouts.py` is right, and **CI is green on
this because CI runs plain Postgres, where the same code works.** ADR 0008 makes
Neon the production database, so the protection C12 was written to provide is not
present where it matters. This is the same lesson as D23 in a new costume: a test
whose result depends on which Postgres it met can be green in the place nobody
deploys to and red in the place everyone does.

**Fixed.** The three are issued with `set_config(name, $n, false)` on the pool's
`connect` event — once per physical connection, so one extra round trip per
connection rather than per request. `set_config` rather than `SET` because `SET`
takes no parameters and these values come from configuration; `false` rather than
`true` because a `SET LOCAL` would be discarded by the first commit and leave
every later user of that pooled connection unprotected.

`application_name` deliberately stays in `server_settings`. It was never dropped,
and it is the control that distinguishes "the startup packet is filtered" from
"the connection is broken" if this regresses.

**Proved by planting the regression.** Putting the three back into
`server_settings` turns `test_db_timeouts.py` red against Neon — and leaves it
green against stock PostgreSQL, which is the honest shape of the problem and is
now stated in that file's docstring. No run against one database can prove a
claim about the other.

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
| **The Actions run** | ✅ **Green in Phase 2** — run [33730363386](https://github.com/xi-4206pbhoite/nexus-os/actions/runs/33730363386), 667 tests executed on a remote runner. Phase 0's claim that this was already true was wrong; see §2 | — |
| **Push access** | This machine authenticates as `xi-4206pbhoite` and is **denied on `upstream` (`parul-bhoite/nexus-os`)**, which is what `dev` tracks. Phase 2 was pushed to `origin` (`xi-4206pbhoite/nexus-os`) instead, and CI ran there. The two remotes have now diverged and only you can reconcile them | Landing Phase 2 on the canonical repository |
| ~~**D23**~~ | ✅ Answered and done — Neon reset to the repository's head, schema recorded first in `doc/archive/` | — |
| **D3** | Google API credentials | P18 (GA4, Search Console), Google sign-in |
| **D10** | Confirm Zoho as the CRM with the first design partner | P18, P19 |
| **D13** | Anthropic access and model tier per execution mode | P14, P20 |
| **`doc/11` §5.4** | The five business calls — B2, B3 and B5 shape the build | P16 onward |
| **Neon is two migrations behind** | It is at `0009`; head is `0011`. `alembic upgrade head` applies Phase 1's `0010` and Phase 2's `0011`, and **0011 drops `preview_session`** — so it is a data-destroying step on your database and was deliberately left for you | Running the suite locally |

Everything else `doc/11` settled. Nothing in Phase 3 is blocked.

---

## 7. Pending work list

Cleared in Phase 0: **C5** (Postgres in CI, fail on skip), **C6** (Alembic both
directions), **M9** (coverage, `--strict-markers`, type-check `tests/`).

Cleared in Phase 1: **C1** (`review_state`), **C2** (`'superseded'`), **C7** (the
no-op validator), **C8** (`NEXUS_ENV` fails closed), **H10** (correlated
exception handler), and **M6** (constraint drift detection, as
`test_constraint_enum_parity.py`). **C12** (database timeouts) was reopened
between Phase 2's discovery of finding #15 and its fix, and is closed again —
the three server-side timeouts now apply on Neon, not only in CI.

Cleared in Phase 2: the preview retirement itself, which had no work-item ID —
it is `doc/12` §Phase 2 in full. **H9** shrank rather than closed: of its three
test mirrors,
`expire_previews`' died with the code it mirrored, and `check_and_increment` and
`scoped_connection` remain.

**Nothing critical fails at runtime.** Every 🔴 below is a feature that does not
exist yet.

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
| 🟠 | H9 | Retire the two remaining test mirrors | P4 | `expire_previews`' mirror died with the preview, as predicted. `check_and_increment` is still mirrored by a synchronous `consume` in `test_rate_limit.py` — so the re-keyed limiter is proved through a copy of its SQL, not through itself — and `scoped_connection` is mirrored too. Not folded into P2: the brief's build list does not carry it, and `scoped_connection` is P10's ground | C5 ✅ | 1.5 d |
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
| 🟡 | M16 | Pin the dependency set — a lockfile and `pip-sync` in CI | P4 | Finding #16. No lockfile today, so every CI run resolves fresh. Two defects landed from this in Phase 2 alone, and the first hid the second | none | 0.5 d |

**M2 (preview deletion path) is void, and now actually so** — Phase 2 deleted
`POST /preview` and migration 0011 dropped `preview_session`, so no data about a
company without an account is collected and there is nothing to expire or
delete. **D9 is marked void in `DECISIONS-REQUIRED.md`**, and finding #14 in
`AUDIT-FINDINGS.md` narrows to re-verification alone.

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

**Phase 3 — Identity.** Email that actually sends, password reset, and one
person to one company. `doc/11` settled the transport, so nothing external
blocks it: `FileMailer` writes `.eml` files into `.mail\`, which means the whole
verification and invitation chain can be built and tested locally and **D4 gates
deployment rather than development**.

It closes §4.5 — `send_verification` has zero callers today, so
`email_verified_at` can never be set, the EMAIL domain-verification method is
unreachable, and an invitation is delivered by the inviter copy-pasting a raw
token URL. It also picks up **M7**, the four config settings held back until
email exists.

One thing Phase 2 hands it, and it is not blocking:

- **Neon is two migrations behind.** `alembic upgrade head` applies `0010` and
  `0011`. `0011` drops `preview_session`, so it destroys data on your database —
  which is why Phase 2 did not run it for you.

And one it hands **P5**, which owns the domain-claim routes: three of the four
routes in `app/routes/onboarding.py` authenticate inside the handler rather than
through `CurrentSession`, so no structural check can see it. `/domains/{id}/check`
performs a server-side fetch, and it is now the only unmetered one left.
