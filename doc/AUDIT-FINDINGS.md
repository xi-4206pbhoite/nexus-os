# Audit findings - 18 August 2026

Four parallel audits (code hygiene, security, frontend, backend) against the
working tree. Records what was found **and what was done**, because a finding
fixed silently and one deferred silently look identical six weeks later.

---

## Fixed while finishing M5 (tasks 5.6 / 5.7)

Nine defects. Each was found by doing something no previous pass had done, and the
list is worth reading as a set — every entry is a *method*, not a lucky catch:

- installing the API from `pyproject.toml` into a clean environment;
- writing a chunk to the real database through the production statement rather than
  a substituted one;
- running the stack end to end against the real embedding model;
- building the connection step, which forced every source to declare what it unlocks;
- configuring an API key **without** the optional SDK;
- completing the registration flow as a customer in the product's actual market.

Two of them are the same failure the entries below describe — *the suite
asserted the shape the route meant to write, not the shape Postgres accepts* —
which suggests the pattern is structural rather than a lapse. The countermeasure
added with them is `tests/test_chunk_embedding_roundtrip.py`, which drives the
production spelling of every value against a live Neon instance and iterates
`ReviewState` rather than listing it, so a future member the CHECK constraint
rejects fails immediately.

### The reporting-currency list had no Omani rial

Found by completing setup as an Omani company and being told `'OMR' is not an
option`. `CURRENCIES` offered AED and SAR — and AUD, CHF, ZAR — but not the currency
of the market the product is built for. The sign-up form's own placeholder is
`you@yourcompany.om`.

Doc 08 §1.3 lists it first (*"OMR — Omani rial · AED — UAE dirham · SAR — Saudi
riyal"*) and doc 01 §3's regional principle names "OMR/AED/SAR". Currency decides
"every monetary figure, every threshold, all formatting", so this was not cosmetic:
an Omani customer could not answer a required question truthfully, and completing
setup was impossible without picking a currency they do not report in.

Added, and sorted first rather than alphabetically — a select whose most likely
answer sits eleventh is a select that gets mis-answered.

### `/health/ready` reported a language model that could not be called

Found by configuring an API key without installing the optional SDK — the exact state
`.env` was already in. `AnthropicProvider.status()` returned `AVAILABLE` on the
presence of a key alone and never checked that `anthropic` was importable, so
readiness said `language_model: ok` while any call raised.

That breaks the promise `app/ai/contracts.py` makes in as many words: *"`availability()`
answers before any call is made, so a dashboard can render 'this needs an API key'
instead of catching an error from a call it should never have attempted."* It holds
only if the check covers both halves — a key **and** the package.

Fixed with a `find_spec` probe, the same way `app/embedding/fastembed_provider.py`
already handled the identical case; `status()` still never imports the SDK, so a
readiness probe stays cheap. Readiness now says: *"An API key is set but the anthropic
package is not installed — run pip install -e \".[ai]\""*.

### Search Console unlocked nothing

Found by building the connection step, which asks each source what it would unlock.
`Source.SEARCH_CONSOLE` was defined in the enum, given a label, and listed in **no
offering's `needs`** — so `offerings_needing` returned nothing for it and the step
would have offered a tool that changes no tile.

Doc 05 §3.7 is explicit that SEO Intelligence's rankings *"need Search Console"*, and
§3 counts it among that offering's sources; `dashboards.py` carried it in the
offering's prose `note` and left it out of the data. Two consequences, and the second
is the worse one: connecting it would have changed nothing, and 3.7 would have
rendered **Live** on DataForSEO plus the crawl alone while its ranking half had no
data source at all — a partial capability presented as a whole one.

Fixed by adding it to 3.7's `needs`, which is what makes that offering render
**Partial** rather than Live in exactly the case doc 05 describes.
`test_no_offered_tool_unlocks_nothing` now holds the general rule, since a tool that
unlocks nothing is always one of two bugs: either it should not be offered, or an
offering's `needs` is missing it.

### Provenance could not distinguish two incompatible embeddings

Found by running the real model rather than the test double. fastembed 0.8.0
embeds `multilingual-e5-large` with mean pooling where 0.5.1 used the CLS token —
different vectors, identical model name, announced only in a `UserWarning`. ADR
0003 stores `embedding_model_id` per chunk row so a future migration can identify
what needs re-embedding *without guessing*; the model name alone cannot, and
vectors from the two poolings do not share a space, so a mixed table degrades
retrieval silently instead of failing. Provenance now carries the library version:
`intfloat/multilingual-e5-large@fastembed-0.8.0`.

`filterwarnings = ["error"]` would have caught the warning, but no test loads the
real model — the deterministic double is what keeps CI fast, and it also makes this
class of upstream change invisible to the suite.

### One onboarding question never said why it was asked

`preferred_terms` omitted `why=`, so it defaulted to empty while all thirteen
others carried one. The `why` is what answers "why are you asking me this?", so a
blank one is a small hole in the same auditability posture I9 sets for numbers.
Filled in.

### No chunk could ever be written to a real database

`ReviewState.NEEDS_REVIEW` was `"needs_review"`. Migration 0007's
`ck_chunk_review_state` allows `('auto_approved','pending_review','approved',
'rejected')`, and `_record` writes `review_state.value` straight into the column.

Since no classifier exists yet, **every** chunk withholds through that member — so
every chunk insert violated the constraint. The M5 upload path could not store a
single chunk, and the review queue's `WHERE review_state = 'pending_review'` could
never have matched anything the route wrote. `HUMAN_APPROVED` was wrong the same
way (`"human_approved"` vs `approved`), and `QUARANTINED` was a value the chunk
constraint has never allowed at all.

Fixed by making the enum carry the database's vocabulary. No test changed: every
one referenced the members, never the strings, which is exactly why the drift was
invisible.

### Superseding a document rolled back its replacement

`app/routes/documents.py` retires a replaced document with
`UPDATE document SET status = 'superseded'` (doc 06 §6). `ck_document_status` did
not list `superseded`, so the UPDATE raised `CheckViolation` — and because it
shares the upload's transaction, the *replacement* rolled back too. Uploading a
new version of a price list would have failed outright and left the old one
authoritative, in the module doc 01 §5 M8 calls the highest-liability one in the
product. **Migration 0010** adds the status.

### A clean clone could not pass CI

`app/connectors/extract.py` imports `bs4` and parses with `lxml`; neither was in
`pyproject.toml`. `pip install -e ".[dev]"` therefore failed to *collect* ten test
modules. Both were named in `ARCHITECTURE.md` §8 from the start and simply never
reached the manifest. The GitHub workflow has never run (ADR 0002 — no remote), so
nothing caught it; `scripts/ci.ps1` passes because the developer's venv acquired
them some other way.

### Every async database call died on a clean install

`sqlalchemy` was declared without the `asyncio` extra, so `greenlet` was absent
and every async engine call ended in `greenlet_spawn` → `_not_implemented()`. That
is 29 errors across `test_preview_cache.py`, `test_invitation_flow.py` and
`test_email_verification.py`, presenting as a database outage rather than a
missing package. Now `sqlalchemy[asyncio]>=2.0.36`.

Same root cause as the entry above, and the same reason it survived: the venv that
runs the gate was never rebuilt from the manifest it is supposed to describe.

---

## Fixed in the 18 August pass

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

## Open - real, and scheduled

| # | Finding | Where | Why not now |
|---|---|---|---|
| 1 | **argon2 blocks the event loop** - sync CPU work in `async def`, ~40-80ms each. 30 rps of logins against non-existent accounts stalls every endpoint, health probes included | `auth/service.py` | Fix is `anyio.to_thread`, but belongs with the rate limiting it compounds - **D14** |
| 2 | **No rate limiting on `/auth/login` or `/auth/register`** - unlimited credential stuffing; register is an unbounded `app_user` growth vector | `routes/auth.py` | **D14** - needs your answer, a per-account lock is a DoS vector against a named user |
| 3 | **Unbounded response buffering** - `FILE_MAX_BYTES` applied after httpx reads the whole body; a multi-GB response OOMs the API | `connectors/domain_check.py:163` | Fix is the crawler streaming pattern; needs its own test |
| 4 | **`/domains/{id}/check` is an unmetered outbound reflector** - the reflected-DoS shape `PER_DOMAIN` stops on the preview path | `routes/onboarding.py:147` | Needs the rate-limit decision alongside #2 |
| 5 | **Blocking untimed `getaddrinfo` on the event loop**, from the one unauthenticated endpoint | `connectors/ssrf.py:138` | `run_in_executor` with a timeout, or `dns.asyncresolver` with a `lifetime` |
| 6 | **`env` defaults to `local`** - a missing `NEXUS_ENV` in production serves `/docs` and sets `secure=False` on both cookies. **Cookies over plain HTTP from one unset variable** | `config.py` | Wants a startup refusal - a deployment-behaviour decision |
| 7 | **The no-usable-default guarantee is a no-op validator**; `session_secret` is declared and referenced nowhere - dead config presenting as a security control | `config.py:102` | Same change as #6 |
| 8 | **No global exception handler**, and `x-request-id` is dropped on the error path - every 500 is uncorrelatable, the one case the header exists for | `main.py` | Grouped with #6/#7 |
| 9 | **Double-clicking create-workspace self-disputes the user own claim**, permanently breaking onboarding. Concurrent race handled, sequential one not | `auth/domains.py:232` | Needs the idempotency test |
| 10 | **Register race returns a 500**, defeating the anti-enumeration response - a distinguishable reply is what that design prevents | `auth/service.py:64` | Catch `IntegrityError` |
| 11 | **Network I/O inside an open DB transaction** - ten concurrent slow checks exhaust the pool | `routes/onboarding.py:156` | |
| 12 | **No connect or statement timeout** on the database | `db.py:37` | |
| 13 | **Email verification never wired** - `send_verification` has zero callers, so no token can exist, so the EMAIL domain method is structurally dead | `auth/email_verification.py` | Blocked on **D4** |
| 14 | **Re-verification and third-party deletion unimplemented**, not merely uncalled - the second is the deletion path a crawled company would use | `auth/domains.py:341` | Part of **D9** |

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
