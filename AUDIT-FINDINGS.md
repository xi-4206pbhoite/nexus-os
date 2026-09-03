# Audit findings - 18 August 2026

Four parallel audits (code hygiene, security, frontend, backend) against the
working tree. Records what was found **and what was done**, because a finding
fixed silently and one deferred silently look identical six weeks later.

---

## Fixed in this pass

### No workspace could be created, and no member could see one

Two defects on the same path, found while building the onboarding wizard on top
of it. Either alone would have made every workspace-scoped route in the product
unreachable. Together they meant M3's success path had never run against a real
database.

**`create_workspace_for_claim` could not insert a workspace.** `workspace`
carries `FORCE ROW LEVEL SECURITY` like every other workspace-scoped table, and
its `WITH CHECK` compares the new row's `workspace_id` against
`nexus.workspace_id`. The function let the database generate both values - which
made `workspace_id` a *different* random uuid from `id` - and set the GUC
afterwards. Postgres refused every insert with `new row violates row-level
security policy for table "workspace"`. The id is now minted in Python, the GUC
set before the insert, and `id` and `workspace_id` written equal, which is what
migration 0002's own comment means by *"`workspace_id` mirrors `id`"*.

**`memberships_for_user` returned nothing for genuine members.** It joins
`membership` to `workspace` to read the name and tenant, and `workspace` was
reachable only with the workspace GUC set - which login cannot do, because which
workspace is precisely what that query is trying to find out. So login reported
zero workspaces, `current_scope` answered `403 No workspace membership` to
everyone, and documents, the review queue and the new setup routes were all
unreachable. Migration **0008** adds a narrow SELECT policy on `workspace` for
users holding a live membership - the same shape and the same argument as
migration 0003, which solved this one table too early.

Neither was caught because **every test that needs a workspace inserts one
itself**, with `id` and `workspace_id` equal and the GUC already set - so the
suites tested the shape the application was supposed to write rather than the
shape it did. `tests/test_invitation_flow.py` now drives `memberships_for_user`
from login's actual position: an identity, and no workspace context.


### The expiry sweep had never run, in any deployment

`app/jobs/scheduler.py` passed `next_run_time=None` to `add_job`. That is not
"no opinion" - it is APScheduler's representation of **paused**. A first fire
time is computed only when the attribute is absent, so setting it to None meant
one never was. The comment two lines above said *"Run shortly after start so a
long-lived process is not the only thing standing between expired data and its
deletion."* The code did the opposite of its own comment.

1. **Preview audits of companies with no account here were retained
   indefinitely.** `jobs/expiry.py` calls this an obligation to a third party
   who never consented to the crawl.
2. `rate_limit_counter` grew without bound on the unauthenticated path.
3. `domain_claim` rows stayed `pending` forever.

Nothing caught it: the module had **zero tests**, and startup logged
`scheduler.started jobs=[expiry_sweep]` throughout - confirming the job was
*registered*, which was true, while saying nothing about whether it would fire.
`tests/test_scheduler.py` now asserts every job has a fire time. Four lines.

### The per-IP rate limit was completely bypassable

`apps/web/app/api/preview/route.ts` forwarded the browser own `X-Forwarded-For`
verbatim. The API trusts that header from this proxy, so any caller could send
`X-Forwarded-For: 1.2.3.4`, vary it per request, and land in a fresh bucket
every time. One machine could spend the entire daily crawl budget and lock out
every real visitor. The sibling `lib/auth-proxy.ts` had always used a header
allowlist for exactly this reason - the preview proxy was the one that got it
wrong. Now takes the address from `request.ip` or `x-real-ip`, neither settable
by a browser; absent both, the header is omitted and the API falls back to its
direct peer - a worse limit but a safe one.

### CSRF failed open in the scenario it was built for

`app/auth/csrf.py` returned early when the CSRF cookie was absent, reasoning no
cookie meant no session to protect. It does not hold: the two cookies have
independent lifetimes, and a sibling subdomain can evict one by filling the
cookie jar. The docstring says the module exists for the cases where SameSite
fails - eviction is on that list. The test justification was wrong too: it
claimed rejecting would break login, but `require_csrf` guards five routes and
**all five already require a session**. Login and register never used it.

### An unauthenticated endpoint leaked the deployment layout

`/health/ready` returned `str(OSError)` for a storage failure, rendering the
absolute path and errno. The database branch twenty lines above already used
`type(exc).__name__` with a comment explaining why. Storage was missed.

### Redaction was eating the telemetry it was not aimed at

`_SECRET_HINTS` held the bare string `token`, substring-matched against key
names, so `input_tokens` and `output_tokens` rendered as redacted on every
`ai.completion` line. The token budget (task 8.6) and drift signal (task 13.4)
had no data source. Now anchored to `_token`, `token_` and specific names.

### The Preview form never showed an error - any error

`AnimatePresence mode="wait"` holds the entering element until the exiting one
finishes animating, and under React 18 StrictMode framer-motion can drop that
completion callback. The running line never finished exiting, so the error line
never mounted. **Every failure was silent**: SSRF refusals, rate limits and
timeouts all looked identical to nothing happening. Second time this pattern
has bitten this codebase - the loop panel froze the same way. Replaced with a
single keyed child, which cannot deadlock: there is no second element to await.

### A reachable render crash, with no boundary to catch it

`PreviewForm` assigned `payload.detail` into a `string`. That holds for errors
the API raises deliberately, but **FastAPI validation errors carry an array of
objects** - a URL over 2048 chars produced one, React was handed an object as a
child, and with no `error.tsx` the page went white. Fixed at the boundary
(`lib/api-error.ts`, shared with `auth-client`) and behind it: `app/error.tsx`
and `app/not-found.tsx` now exist. The error page shows the digest, not the
message, because a render error can carry customer content.

### Nine dead controls, two of them consequential

`FinalCta` two buttons were `href="#"`, and every other Start free pointed at
`#cta`, which contained only those two - so **a visitor could not create an
account from the landing page at all**. `/register` was reachable only from
`/login`. Seven footer links were also dead, including **Privacy and Terms**.
Those two are removed rather than pointed somewhere plausible: a link to a
privacy policy that does not exist implies a document a customer could rely on.
They belong back the moment the pages are written, and before anyone signs up.

### Content-rule violations in the most prominent product imagery

CLAUDE.md forbids invented customers and requires product mocks to carry a
visible Illustrative tag. The hero Morning Brief and Health Score cards carried
invented figures with no tag; LoopMock carried the tag but also an invented
customer name, which the rule forbids outright. Both cards are tagged now and
the name is gone. A footnote at the page bottom was not sufficient - these
cards are screenshot-shaped, and the screenshot travels without the footnote.

---

### The test suite read the developer's API key

`tests/conftest.py` exists to pin the suite to a known-unconfigured baseline, and
its docstring says why: before it, a real `NEXUS_DATABASE_URL` in `.env` changed
the suite's *result*, which is worse than a failing test because it passes in CI
and fails on the machine that wrote it.

`NEXUS_ANTHROPIC_API_KEY` was not in the pinned list. On a machine with a key
configured, `/health/ready` reported `language_model: ok` during tests, which is
why `test_readiness_reports_the_language_model_but_never_gates_on_it` had to
accept `state in {"ok", "unconfigured"}` to pass anywhere - the tolerance was the
symptom. It also left a live key reachable from the suite, one careless test away
from a billable call.

Found while adding the embeddings readiness check, because the same probe printed
the AI provider's status next to it.

### A concurrent session corrupted a spike's measurements

The first run of `scripts/spike_ann_recall.py` produced a plausible recall table
that measured nothing. Three of the four causes were in the script (isotropic
vectors, seq scans reported as recall, an unrecorded `ef_search`); the fourth was
that another session held an `ann_spike` table of its own shape and was creating
and dropping indexes on it, so ground truth and measurement could come from
different table contents.

The spike now namespaces its table and indexes per process. The test suite was
checked and is **not** exposed - every test runs in a transaction that is always
rolled back, with fresh UUIDs - but ad-hoc scripts doing DDL under fixed names on
a shared database are. Recorded because the fix is a habit, not a patch: one Neon
instance serves several sessions.

## Open - real, and scheduled

Reconciled with `BUILD-STATUS.md` in Phase 2. Four rows (#6, #7, #8, and the
code half of #12) had been fixed in Phase 1 and never struck from this table, so
the register said fourteen open findings while the code said ten. Two new
findings were added in the same pass. **#15** is what running the suite against
Neon rather than the CI container turned up. **#16** is what running CI at all
turned up — the test step had not executed since M5, and nobody could have known,
because the job failed at an earlier step that looked unrelated.

| # | Finding | Where | Why not now |
|---|---|---|---|
| ~~1~~ | ~~**argon2 blocks the event loop**~~ - **fixed in P4.** `anyio.to_thread` in `auth/passwords.py`; `authenticate`, `register_user` and the dummy-hash equaliser all await it now. Thirty guesses a second at a non-existent account no longer hold the loop's only thread | `auth/passwords.py` | Closed |
| ~~2~~ | ~~**No rate limiting on `/auth/login` or `/auth/register`**~~ - **fixed in P4**, as D14 specified: per-IP and per-email counters, exponential backoff, an identical 401 in every case. Never a 429 (keyed by email it confirms an address exists) and never a lock (a denial-of-service vector against a named user) | `routes/auth.py` | Closed |
| ~~3~~ | ~~**Unbounded response buffering**~~ - **fixed in P4.** It was `client.get()` then `response.content[:FILE_MAX_BYTES]`, which caps the *slice* and not the read: httpx had already buffered the whole body by the time the slice ran, so a domain check against a multi-GB response took the API down with it - and the caller chooses the target. Now streamed with `aiter_bytes` and stopped at the cap, the way `research/crawler.py` always did it | `connectors/domain_check.py:174` | Closed |
| 4 | **`/domains/{id}/check` is an unmetered outbound reflector** | `routes/onboarding.py:147` | Needs the rate-limit decision alongside #2. **Phase 2 made this worse, not better:** the note used to read "the reflected-DoS shape `PER_DOMAIN` stops on the preview path", and `PER_DOMAIN` is now deleted. This is the only unmetered outbound fetch left, and the route declares no session dependency |
| 5 | **Blocking untimed `getaddrinfo` on the event loop** | `research/ssrf.py:138` | **Re-deferred, with a reason.** `validate_url` is synchronous and called from six places including the 89-case SSRF suite; making it `async` is a signature change that ripples through all of them, and `run_in_executor` inside a sync function needs a running loop it cannot assume. Both are real refactors rather than a patch, and neither should be rushed into a phase that has already changed this file's neighbours. **Its reach shrank in P2** - it was reachable from an endpoint open to anyone and is now only on the domain-claim path, which P4 also put behind a per-IP counter. Take it with the P5 work on those routes |
| ~~6~~ | ~~**`env` defaults to `local`**~~ - **fixed in Phase 1.** `env` has no default, so a missing `NEXUS_ENV` refuses to boot; `is_local` was replaced by `cookies_secure` and `docs_enabled`. ADR 0015 | `config.py:34` | Closed |
| ~~7~~ | ~~**The no-usable-default guarantee is a no-op validator**~~ - **fixed in Phase 1.** `session_secret` is deleted and `_required_in_deployed_envs` is a real startup refusal | `config.py:89` | Closed |
| ~~8~~ | ~~**No global exception handler**~~ - **fixed in Phase 1.** A 500 now carries `x-request-id` in the body and the header; `tests/test_error_correlation.py` asserts it | `main.py` | Closed |
| ~~9~~ | ~~**Double-clicking create-workspace self-disputes the user's own claim**~~ - **fixed in P4.** The claim now carries the workspace it produced, so a repeat is told from a genuine dispute and returns the existing workspace idempotently. The concurrent race was handled and the sequential one was not, which is the likely one - a double-clicked button, a retried request, a browser replaying a POST. Falling through marked the user's own claim disputed against their own workspace, permanently, with no path forward short of editing the database | `auth/domains.py:250` | Closed |
| ~~10~~ | ~~**Register race returns a 500**~~ - **fixed in P4.** `IntegrityError` from the check-then-act is caught and converted to the same refusal the sequential path raises. It was not merely an ugly error: register answers identically for a new and a known address *precisely* so it cannot reveal who has an account, and a 500 on exactly the addresses that already exist is the distinguishable reply that design prevents - widenable by registering the same address twice on purpose | `auth/service.py:71` | Closed |
| ~~11~~ | ~~**Network I/O inside an open DB transaction**~~ - **fixed in P4.** `check_claim` split into `load_claim_for_check` -> `perform_check` -> `record_check_result`, with **no session held across the network call**. `perform_check` takes no session at all, so the guarantee is structural rather than a comment asking the next caller to be careful. Outside the `async with` rather than after a commit: a commit ends the transaction and keeps the connection, which is the resource that ran out | `routes/onboarding.py:157` | Closed |
| ~~12~~ | ~~**No connect or statement timeout** on the database~~ - **fixed in Phase 1, and actually in force since #15 was closed.** Four timeouts, three server-side and one client-side, now proved live on Neon as well as on stock PostgreSQL | `db.py:37` | Closed |
| ~~13~~ | ~~**Email verification never wired**~~ - **fixed in P3**, and this row should have gone with it. `POST /auth/register` calls `issue_verification` and queues the send; `email_verified_at` can be set, so the EMAIL domain-verification method is reachable for the first time. Verified against a live app in P5's walkthrough: register -> `.eml` on disk -> token verifies -> second use refused. **Not blocked on D4 after all** - `FileMailer` makes the whole chain work with no provider, which is what D4 was thought to gate | `routes/auth.py` | Closed. Caught by reading this register back rather than by anything failing, which is the argument for reading it back |
| 14 | **Re-verification unimplemented**, not merely uncalled | `auth/domains.py:341` | The third-party deletion half of this finding is **closed by Phase 2**: no unauthenticated crawl means no crawled company, so there is nothing for such a path to delete (**D9 void**). Re-verification remains open |
| ~~15~~ | ~~**Neon silently discards three of the four database timeouts**~~ - **fixed.** They were in asyncpg's `server_settings`, which becomes the connection's startup packet, and Neon's proxy filters that to an allowlist. Now issued with `set_config(name, $n, false)` on the pool's `connect` event - once per physical connection, so one round trip per connection rather than per request. `application_name` stays in `server_settings`: it was never dropped, and keeping it there is what distinguishes a filtered packet from a broken connection if this regresses | `db.py:126` | Closed. Verified by planting the old `server_settings` version and watching `test_db_timeouts.py` go red **against Neon** |
| ~~16~~ | ~~**The dependency set is unpinned**~~ - **fixed.** `services/api/requirements-dev.lock` pins all 72 packages with hashes, compiled for `--python-platform linux` because that is what the workflow runs. CI installs `--require-hashes -r requirements-dev.lock` then `pip install -e . --no-deps`, and the pip cache keys on the lockfile rather than on `pyproject.toml`, which only states ranges. Ranges stay in `pyproject.toml`: they say what the code *supports*, which is a different claim from what CI *ran* | `services/api/requirements-dev.lock` | Closed. Regenerate with the `uv pip compile` line in the file's header and read the diff — it is the only place an unintended upgrade is visible |
| 17 | **A rolling session has no absolute cap** - P4 made the twelve-hour window extend on activity (`doc/11` §5.2), so a session in continuous use never expires. That is the intent for someone working a long day and equally the effect for whoever else holds the cookie: a stolen session stays alive as long as it is used, which is exactly the property the fixed window was described as providing | `auth/service.py:resolve_session` | Raised by the work that caused it. The usual answer is an absolute cap on `created_at` alongside the rolling `expires_at` - the column exists. **Not implemented because it is a product call**: a cap signs people out mid-task on a schedule they cannot see, and `doc/11` §5.2 specifies the rolling refresh without one |
| ~~18~~ | ~~**"First verified wins" has never worked**~~ - **fixed.** The detection query moved to `find_verified_workspace_for_domain`, which asks as `nexus_jobs` through a role-targeted SELECT policy (migration 0015) rather than on the caller's session, where `workspace`'s RLS made a rival claimant invisible. Both call sites now use it - `create_workspace_for_claim`, where the dispute branch had never executed since M3, and P5's duplicate-domain branch, which inherited the same silence. Nothing was ever corrupted: the partial unique index refused the second verification anyway, but as a constraint violation, so the user saw a 500 instead of "that company is already here" and no dispute record was written | `auth/workspaces.py` | Closed. The grant extends `nexus_jobs` from one table to two; ADR 0018 required that be argued, and migration 0015 carries the argument - the *write* half of this operation already ran as `nexus_jobs`, so leaving the read on the app role split one decision across two identities |

---

## By design - looked wrong, is not

- **Every API process runs the scheduler.** Stated in the docstring with the
  threshold at which it stops being acceptable. The sweep is idempotent.
- **`str(exception)` in five response bodies.** All authored constants;
  `domains.py:50` states the contract. The one real leak is fixed above.
- **Most of `app/documents/`, `app/retrieval/` unreachable from any route.**
  Forward-built for M5/M6 and documented as such.

---

## Method note

In four places the *comments* exposed the defect rather than concealing it:
the scheduler run-shortly-after-start, config no-usable-default, the crawler
total-budget, and health database-branch versus storage-branch. In each case
the prose stated the correct intent and the code diverged from it.

A good failure mode to have - and an argument for testing the claims the
comments make.
