# NEXUS OS — how to run and test what exists

**As of 17 August 2026.** Every claim here was executed against the running
system before being written down. Where something does not work, this says so
rather than describing the intention.

---

## Read this first: no, not every feature is built

You asked whether everything is implemented. It is not, and the gap is large.

| | |
|---|---|
| **Milestones complete** | M0, M1, M2, M3, M4 |
| **In progress** | M5 — 5 of 12 tasks done |
| **Not started** | M6 through M13 |
| **API endpoints** | 12 |
| **Web pages** | **1** — the landing page |
| **Signed-in UI** | **none** |
| **Tests** | 459, green against the real database |

The one sentence that matters: **the only feature with a user interface is the
Preview audit on the landing page.** Everything else that exists is reachable
only by HTTP call or from the test suite. There is no dashboard, no document
upload screen, no AI director, no morning brief — those are M6 onward.

What *is* built is the foundation those depend on: tenant isolation enforced by
the database, the permission lattice, the workspace gate, and the document
pipeline's parsing and classification. That is deliberate sequencing, not an
oversight — doc 07 puts the security core before the features, because retrofitting
it is how these products leak.

---

## Starting it up

The database needs no action. It is Neon (ADR 0008), always on, already
migrated. There is nothing to start locally.

**Terminal 1 — the API**

```powershell
cd services\api; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

**Terminal 2 — the web app**

```powershell
npm run dev --prefix apps\web
```

**Terminal 3 — prove it all works**

```powershell
.\scripts\smoke.ps1
```

That script is the fastest honest answer to "is it working?" It walks every
endpoint, prints what it is about to prove, and **asserts the refusals as well as
the successes** — a CSRF-less POST, a workspace for a domain you do not own, six
hostile URLs. A smoke test that only walked the happy path would pass just as
happily with every guard removed.

Expect `SMOKE PASSED   17 assertions`. Two things it may legitimately skip:

- **`429 rate limited`** — the Preview audit is capped at 5/hour per IP and
  3/day per domain, and the script's own six SSRF probes spend that same
  allowance. Re-running inside the hour will hit it. Use `-SkipPreview` to run
  the rest, or `-PreviewUrl https://another-site.com`.
- **`did not answer`** — the site you pointed it at is slow or blocking us.
  Not a defect; the API says which it was.

---

## 1. What you can test in a browser

Open **http://localhost:3000**.

### The Preview audit — the whole of the clickable product

Type a real website into the hero field and press **Analyse my business**. No
account needed. It fetches the page server-side and scores it.

Verified live on `omantel.om`: **72/100 across 3 scored categories**, 23 checks,
7 locked categories.

Four things are worth looking at closely, because they are the product's
central promises made visible:

**Every number carries its evidence.** Expand any category. Each check states
what it found — `title: 'Personal | Omantel'`, `913 words`, `46/46 images`,
`36 script tags`. Nothing is a bare score. A test walks the route's import graph
and fails if any model layer is reachable from it, so no figure here came from a
language model (I1, I9).

**Locked is never zero.** Marketing, Sales, Finance, Operations, People, Customer
Experience and Competitors each render with the specific thing that would unlock
them — "Connect Google Analytics", "Invite your team". A dashboard showing `0`
for a category it cannot measure is the failure mode this exists to prevent (I10).

**The reduced audit is honest about being reduced.** The note under the result
says competitor discovery and keyword data are withheld until you verify you own
the domain. That limit is real, not decorative: anyone can type a competitor's
address, and without it this would be a competitive-intelligence tool sold by
accident.

**Try to break the fetch.** Enter `http://169.254.169.254/`, `http://10.0.0.1/`,
or `http://2130706433/`. All refused. This is an unauthenticated server-side
fetch where the caller picks the destination, so the guard validates the URL,
pins the resolved IP, connects to *that address*, and re-validates every redirect
hop by hand.

Audits expire after **7 days**.

### What is on the page but not wired up

The header's **Sign in** link is `href="#"`. There is no sign-in UI. The rest of
the landing page — the loop panel, pillars, pricing, FAQ — is content, not
function.

---

## 2. What you can test through the API

Interactive docs: **http://127.0.0.1:8000/docs**

All 12 endpoints, and what each is good for:

| | Endpoint | Notes |
|---|---|---|
| GET | `/health` | Liveness. Never touches the database, so an outage cannot cause a restart loop. |
| GET | `/health/ready` | Readiness. Reports each dependency separately. **~1.8s** — see troubleshooting. |
| POST | `/preview` | The audit. Unauthenticated, rate limited. |
| POST | `/auth/register` | Returns `check_your_email` whether or not the address exists. **Sends no email — see Wall 1.** |
| POST | `/auth/login` | Sets `nexus_session` and a readable `nexus_csrf` cookie. |
| GET | `/auth/me` | **Requires a workspace membership — 403 without one. See Wall 2.** |
| POST | `/auth/logout` | |
| POST | `/auth/workspace` | Switch active workspace. Needs ≥2 memberships to be meaningful. |
| POST | `/auth/verify-email` | Consumes a token. **Nothing issues one — see Wall 1.** |
| POST | `/domains` | Begin a domain claim. Returns the challenge and instructions. |
| POST | `/domains/{id}/check` | Attempt verification. |
| POST | `/domains/{id}/workspace` | Create the workspace. Refused unless the domain is verified. |

Every state-changing call needs `X-CSRF-Token` matching the `nexus_csrf` cookie.
`smoke.ps1` handles all of this; read it if you want the exact shapes.

### Guarantees you can check yourself

- **No account enumeration.** A wrong password and an unknown address both return
  `401 {"detail":"Invalid email or password"}` — identical status *and* body.
  Registering an existing address returns the same `check_your_email` as a new
  one.
- **The workspace gate.** M3's acceptance test is "try to create a workspace for
  a domain I don't control and fail." Verified: `403 Verify the domain before
  creating a workspace.`
- **Failures state a reason.** Checking an unproven claim returns
  `No TXT records found for this domain.` — not a silent `false`.

---

## 3. Three walls you will hit

These are real gaps, not misconfiguration. Knowing them will save you an hour.

### Wall 1 — no verification email is ever sent

`email_verification.issue()` exists, is tested, and **is never called by any
route**. Registration returns `check_your_email`; no email is written to
`.mail\`, and no token is created.

Consequences: `POST /auth/verify-email` cannot be exercised without inserting a
token directly into the database, and the `email` method of domain claiming is
unreachable because it requires a verified address.

### Wall 2 — a fresh account is a dead end

`GET /auth/me` returns **403** until you have a workspace membership. A workspace
requires a verified domain. So registering and logging in gets you a session that
can do almost nothing.

This is the gate working correctly — it is exactly what stops someone claiming a
domain they do not own — but it means **you cannot see a signed-in state at all
unless you control a domain.** And even then there is no UI to see it in.

### Wall 3 — documents have no way in

M5's parsing, chunking and classification are written and tested. There is **no
HTTP endpoint** to upload a document (task 5.2) and **no embedding step** (5.6).
The `chunk` table and its `vector(1024)` column with an HNSW index exist and are
empty.

So the payroll-file test doc 07 asks you to run — upload something sensitive,
confirm it is not visible until reviewed — **cannot be done through the product
yet.** It can only be run as a test:

```powershell
cd services\api; .\.venv\Scripts\python.exe -m pytest tests\test_classification_default_deny.py -v
```

---

## 4. If you do control a domain

This is the only way to reach a real workspace. Two methods work.

**DNS TXT (strong).** `POST /domains` with `{"domain":"yourcompany.om","method":"dns_txt"}`
returns a challenge. Add the TXT record it names, wait for propagation, then
`POST /domains/{id}/check`, then `POST /domains/{id}/workspace`.

**A file on your website (strong).** Same flow with `"method":"file"`. Publish
the challenge string at `https://yourdomain/.well-known/nexus-domain-verification.txt`.
Often faster than DNS if you can deploy a static file.

First verified claim wins, decided by a partial unique index in Postgres rather
than by application timing. Unverified claims reserve nothing, so nobody can lock
you out of your own domain by typing it first.

---

## 5. Built, tested, but only reachable from the test suite

Substantial work with no HTTP surface yet. The tests are the documentation.

```powershell
.\scripts\ci.ps1
```

| Area | Test file |
|---|---|
| Tenant and workspace isolation, attempted and failed | `test_tenant_isolation.py` |
| Default-deny classification (I4) | `test_classification_default_deny.py` |
| Document parsing and chunking | `test_document_parsing.py` |
| The role/scope matrix | `test_role_scope_matrix.py` |
| The Contributor L3 boundary (ADR 0005) | `test_contributor_scope.py` |
| Scope-keyed cache keys (I5) | `test_scope_cache_key.py` |
| SSRF corpus — 89 cases | `test_ssrf_guard.py` |
| Audit scoring, no model anywhere | `test_audit_calculators.py` |

The isolation suite is the one to read if you read one. It runs as the real
application role against the real database and tries to leak across tenants in
every shape, including targeted reads of a known UUID and writes aimed at another
workspace. Its first assertion is that the role cannot bypass row-level security
— because if that fails, every other test in the file proves nothing.

---

## 6. Does not exist at all

Stated plainly so you do not go looking:

- The seven AI directors, and any agent
- The scoped retrieval layer (M6) — the thing that makes the directors safe
- The Company Brain as a queryable surface
- The morning brief, any dashboard, any chat
- Onboarding wizard UI, and the answer/invitation endpoints
- Integrations: GA4, CRM, accounting — every "Connect…" unlock names a
  capability that is not built
- Arabic (ADR 0003 chose a multilingual embedding model for it; nothing consumes
  that yet)
- Billing, ownership transfer, scheduled domain re-verification

The mocks on the landing page carry a visible `Illustrative` tag for this reason.

---

## 7. Troubleshooting

**The first API call after a restart takes ~6 seconds.** Neon suspends idle
compute. Subsequent calls are ~1.8s for `/health/ready` (it reaches the
database) and fast for everything cached. If the web app reports
`api: timeout`, call it again — that state exists specifically to distinguish
"waking up" from "dead".

**`/health/ready` takes 1.8s and that is expected.** Round trips to `us-east-2`
cost ~450ms each. It was 3.5s until both database checks were folded into one
query.

**The test suite takes ~5 minutes.** Against Neon, every statement is a round
trip. Locally it is ~8 seconds. Not a hang.

**`429 Too many analyses`.** 5/hour per IP, 3/day per domain, 500/day globally.
The global ceiling is the one that bounds cost.

**`Invoke-RestMethod` throws on 4xx.** PowerShell 5.1 puts the response body in
`$_.ErrorDetails.Message`, *not* in `GetResponseStream()` — the stream is already
consumed by the time the exception surfaces.

**Non-ASCII in a `.ps1` string literal breaks the script.** Without a UTF-8 BOM,
PowerShell 5.1 reads the file as CP1252; an em dash becomes three characters, one
of which is a smart quote that terminates the string early. Keep `.ps1` files
pure ASCII.

**Shell.** This project is PowerShell 5.1. No `&&`, no ternary, no `??`. `curl`
is an alias for `Invoke-WebRequest`, so bash flags fail. Prefer the scripts in
`scripts\`.

---

## What to tell me after you test

Most useful:

1. Did `.\scripts\smoke.ps1` pass, and if not, which assertion failed?
2. Does the Preview audit read as credible for a business you know? The scoring
   weights are a first pass and are the kind of thing worth arguing about.
3. Which of M6–M13 do you want next? The retrieval layer (M6) is the gating
   dependency for every AI feature, and M5 task 5.7 — the filtered-ANN recall
   spike — has to be answered before M6 can be designed.

Open decisions waiting on you are in `DECISIONS-REQUIRED.md`: D2, D3, D4, D6,
D7, D8, D10, D11, D12, D13.

Two things I would do before going further:

- **Rotate the Neon `neondb_owner` password.** It was pasted in plain text in
  chat. The application does not use it — it connects as `nexus_app`, whose
  password appears in no tracked file.
- **Retire the native PostgreSQL cluster.** It cannot run pgvector, so nothing
  from migration 0007 onward applies to it. `scripts\pg-local.ps1`,
  `scripts\db-init.ps1` and the fallback branch in `verify.ps1` are now dead
  ends. The Docker path (ADR 0006/0007) stays as the offline fallback.
