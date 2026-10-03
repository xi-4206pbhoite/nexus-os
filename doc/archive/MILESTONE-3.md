# Milestone 3 — Registration and domain verification

**Status:** ✅ complete — **ready for validation**
**Date:** 16 August 2026 · 337 tests · CI green

Doc 07 M3: *"Done when no workspace exists without a verified domain, and Preview data expires."*

---

## Acceptance — verified live

**Attempting to create a workspace for a domain I don't control:**

```
POST /domains            {"domain":"https://www.acme-not-mine.om/about","method":"dns_txt"}
  → domain normalised to acme-not-mine.om, strength "strong", state "pending"

POST /domains/{id}/workspace  {"name":"Stolen Co"}
  → 403  "Verify the domain before creating a workspace."

POST /domains/{id}/check
  → state "pending", evidence "No TXT records found for this domain."

POST /domains/{someone-elses-id}/workspace
  → 403  "No such claim."

SELECT count(*) FROM workspace WHERE domain LIKE 'acme-%'  →  0
```

**Preview data expires:** the sweep runs hourly and `scheduler.started jobs=['expiry_sweep']` appears at startup.

```
=== api: ruff check ===   PASS      === web: tsc ===    PASS
=== api: ruff format ===  PASS      === web: lint ===   PASS
=== api: mypy strict ===  PASS      === web: build ===  PASS
=== api: pytest ===       PASS  (337 tests)
CI GREEN
```

---

## The gate is one function

`create_workspace_for_claim` is the **only** path that inserts a workspace. There is no `POST /workspaces` that takes a domain. Spreading the check across routes would make it a convention; here it is a precondition, and anyone attacking it has one place to aim at.

**First verified wins is decided by Postgres, not by our timing.** The partial unique index on `lower(domain) WHERE domain_verified_at IS NOT NULL` resolves the race — two requests can pass an application-level "does it exist?" check simultaneously, and the `IntegrityError` path is handled as a dispute rather than a 500. The loser gets a `disputed` claim record, because a support conversation about a contested domain needs an artefact.

The uniqueness applies **only to verified domains**, which matters: an unverified placeholder reserving a domain would mean typing a competitor's URL was enough to lock them out.

---

## Methods are not graded on one axis

| Method | Proves | Strength |
|---|---|---|
| DNS TXT | control of the domain's DNS | strong |
| File at `/.well-known/…` | control of the web server | strong |
| Same-domain email | **employment**, not authority | weak |
| Support approval | documentary evidence | weak |

The weak methods aren't lesser versions of the strong ones — they answer a different question. Anyone with a mailbox at a large company passes the email check, so it grants workspace creation but sets `owner_claim_review`, and `verification_method` is stored so support knows *how* a workspace was proved months later.

Two details worth naming:

- **The file check goes through the SSRF guard.** It's a server-side fetch of a user-supplied domain, and the claim is the thing being tested — so it can't be the reason to trust the target. Redirects are refused outright there, since one could leave the domain entirely.
- **A subdomain doesn't prove its parent.** `x@mail.acme.om` proves `mail.acme.om`. Normalising it to `acme.om` would let a subdomain owner claim the whole company, and there's a test for it — along with `acme.om.evil.com`, which naive suffix matching accepts.

Free email providers are rejected for the email method: a `gmail.com` workspace would be a workspace for Gmail.

---

## Preview data actually expires

Doc 06 §10's requirement has an unusual property that shaped the implementation: **the subject of this data is not our user.** A company whose site was crawled by a stranger evaluating them has no login here, can't see what we hold, and can't ask an account manager to remove it.

So expiry is a **hard delete on a schedule**, not a `deleted_at` flag and not a read-time filter — either of those would leave that company's data in the table indefinitely. `delete_previews_for_domain` is the deletion-request path, keyed on the domain rather than an account, because the requester has neither.

A claimed preview is exempt: once the domain is verified, the data belongs to a workspace and falls under that workspace's retention instead. Creating a workspace claims any matching Preview rows.

Stale *claims* are marked `expired` rather than deleted — for a contested domain, who tried is exactly what support needs.

---

## Two bugs found

**RLS caught my own test.** A test asserting two unverified workspaces can share a domain failed on `count(*) == 1`. The code was right: my helper set the workspace GUC per insert, so the count was correctly filtered to the last one. The test now counts under each workspace's own GUC — and reads as a reminder that those rows are never visible together to an ordinary caller.

**`ci.ps1` failed the whole gate on an `npm notice`.** Windows PowerShell 5.1 wraps a native command's stderr in an ErrorRecord, which `$ErrorActionPreference='Stop'` turns into a terminating error — so `tsc` exiting 0 was reported as a failure. This is the exact trap recorded in `CLAUDE.md`, which I'd applied to `db-init.ps1` and never to the gate itself. Both call sites now branch on the real exit code.

---

## What does not exist

- **Registration doesn't send the verification email yet.** `send_verification` and the `FileMailer` both work and are tested, but `POST /auth/register` doesn't call them — so `POST /auth/verify-email` is only reachable with a token minted directly. Wiring is a few lines; I'd rather flag it than claim the loop is closed.
- **No ownership-transfer flow.** Doc 06 §1.1 requires one. Revocation and dispute exist; transfer does not.
- **Re-verification is queryable but not scheduled.** `claims_due_for_recheck` and `revoke_claim` exist and are tested; the hourly job only runs expiry. The cadence itself is one `add_job` call once the recheck behaviour is agreed.
- **Manual/support approval is a recorded method with no admin UI** — deliberately, since doc 06 §1.1 names it the social-engineering target and it should not be easy.
- **The scheduler is in-process.** With more than one API process, every process runs the job. The expiry sweep is idempotent so that's currently harmless, but the first non-idempotent job — sending a brief, charging a card — needs leader election. Recorded in `scheduler.py` so it's a decision rather than an accident.
- **`D4` (production email provider) is still open.** Dev writes `.eml` files to `.mail/`.

---

## How to validate

```powershell
.\scripts\verify.ps1
```

Then try to steal a domain. Register, log in, and:

```powershell
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-RestMethod -Uri http://127.0.0.1:8000/auth/login -Method Post -WebSession $s `
  -ContentType 'application/json' `
  -Body '{"email":"you@example.com","password":"your-password"}'
$csrf = $s.Cookies.GetCookies('http://127.0.0.1:8000')['nexus_csrf'].Value
$claim = Invoke-RestMethod -Uri http://127.0.0.1:8000/domains -Method Post -WebSession $s `
  -Headers @{ 'X-CSRF-Token' = $csrf } -ContentType 'application/json' `
  -Body '{"domain":"bbc.co.uk","method":"dns_txt"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/domains/$($claim.claim_id)/workspace" `
  -Method Post -WebSession $s -Headers @{ 'X-CSRF-Token' = $csrf } `
  -ContentType 'application/json' -Body '{"name":"Not Mine"}'
```

Expect **403 — "Verify the domain before creating a workspace."**

**The most useful thing you can do is find a way past the gate.** It is one function; if there's a route into `workspace` that doesn't go through it, that's worth more than another passing test.

---

## Invariants

| | Status |
|---|---|
| **I2 / I3** | Unchanged — verification runs before a workspace exists, so before any scope does |
| **I7** untrusted content | The file check treats the claimed domain as hostile: SSRF-guarded, address-pinned, redirects refused |
| **I10** never a zero | Failed checks return evidence explaining what was seen, never a silent false |

---

## Next

**M4 — onboarding, persona, scope enforcement.** ⛔ **`D5` is now blocking.** M4's acceptance is *"a Contributor cannot reach L3 aggregates"*, and which department data that covers is undefined — doc 06 §11.5 lists it as genuinely open. My proposed default is in `DECISIONS-REQUIRED.md`; I need you to ratify or correct it before M4 can have a meaningful acceptance test.
