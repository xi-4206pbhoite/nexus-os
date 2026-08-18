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
