# Milestone 1 — Tenancy, auth, roles

**Status:** ✅ complete — **ready for validation**
**Date:** 16 August 2026 · 135 tests · CI green

Doc 07 M1: *"Done when cross-tenant and cross-workspace access is impossible and there are tests that try and fail."*

---

## Acceptance

**Met.** 26 of the 135 tests exist solely to attempt a leak and fail. They run against real PostgreSQL as the real application role — not as `postgres`, which would sail through every policy and prove nothing.

```
=== api: ruff check ===   PASS      === web: tsc ===    PASS
=== api: ruff format ===  PASS      === web: lint ===   PASS
=== api: mypy strict ===  PASS      === web: build ===  PASS
=== api: pytest ===       PASS  (135 tests)
CI GREEN
```

---

## The three things that make isolation real

**1. `FORCE ROW LEVEL SECURITY`, not just `ENABLE`.** A table's owner bypasses its own policies, and migrations run as `nexus_app` — so `ENABLE` alone leaves every policy inert *for the exact role the application connects as*. The suite would have passed while proving nothing. `test_policies_are_forced_not_merely_enabled` asserts `relforcerowsecurity` on all four workspace-scoped tables, and the very first isolation test asserts the app role is neither superuser nor `BYPASSRLS`.

**2. The workspace comes from a GUC the client cannot set.** `retrieval.scoped_connection` sets `nexus.workspace_id` and `nexus.user_id` with `is_local = true` — transaction-scoped, so a pooled connection cannot carry the previous caller's workspace to whoever picks it up next.

**3. Default deny in both directions.** A GUC that was never set is NULL, and `workspace_id = NULL` is NULL, which RLS treats as invisible. A GUC *cleared* to `''` is a different state — and `''::uuid` **raises** rather than denying. The isolation suite caught that: fail-closed, but a 500 on every subsequent query is not a correct answer to "who are you". `NULLIF(..., '')` makes both states a clean deny, and each has its own test.

---

## What exists

### Domain — the security model as data

`ROLE_GRANTS` is a frozen table encoding doc 06 §2.3, not conditionals scattered through handlers. Each of the three corrections doc 06 records has a dedicated test, because each was a real defect:

| Correction | Test |
|---|---|
| The lattice is monotonic | Walks every role up L1→L2→L3 and fails on any hole |
| Contributor ≠ Manager | Contributor's L3 is a restricted subset |
| L4 is unreachable by role | Asserted for **every** role including Owner |

`ScopedSession` carries resolved authority. `cache_key()` keys on *authority* — not tenant, not user — so two callers with identical scope share an entry while an Owner's composite can never be served to a Contributor (**I5**). Seven tests cover it, including that the key leaks no raw identifiers.

### Schema

`tenant` · `app_user` · `workspace` · `membership` · `user_session` · `persona` · `audit_log`, with RLS enabled and forced on the four workspace-scoped tables.

Constraints doing real work: case-insensitive unique email (`Parul@x.com` and `parul@x.com` are one account); one membership per `(workspace, user)` so the effective role is never ambiguous; a role CHECK constraint so no value can exist that the scope table has no row for; `invited_by_user_id` recording who set a role, since doc 06 §2.2 forbids self-declaration.

### Auth

- **argon2id**, OWASP parameters, with `needs_rehash` so raising them later upgrades on next login
- **Session tokens are stored hashed** — a leaked database yields no usable sessions
- **Session fixation is prevented by construction**: login always mints a fresh token, so a planted token is never the one that ends up authenticated
- **Login is not a user-enumeration oracle** — identical error and equalised timing for unknown account, wrong password and disabled account. Registration returns the same body whether or not the email was already taken
- **CSRF double-submit** on state-changing routes, with the session cookie `HttpOnly` and the CSRF cookie deliberately *not* — the client must echo it into a header, which a cross-origin attacker cannot do

### Server-side workspace resolution

There is no `X-Workspace` header, no query param, no body field. The active workspace lives in `user_session` and is **re-validated against current memberships on every request** — a membership revoked mid-session takes effect immediately (doc 06 §4.15), and a stale pointer produces 403 rather than silently falling back to another workspace.

`POST /auth/workspace` is the one place a client may express a preference, and it is validated rather than believed. A workspace that exists but is not yours returns the same response as one that does not exist — existence disclosure is a leak (doc 06 §4.5).

### I2 enforced against the source

`test_retrieval_signatures.py` walks every public callable in `app.retrieval` and fails the build if one accepts a forgeable identity argument. The rule is annotation-aware: `workspace_id: UUID` is rejected, `caller: ScopedSession` is not — the danger is scope arriving as data a caller composes, not the parameter's name. It includes a self-test proving the guard can actually fail.

### Migration 0003 — a deliberately narrow widening

Listing which workspaces you can switch to is inherently a cross-workspace read, which the isolation policy correctly denies. Rather than widen that policy or read memberships as a privileged role — both of which punch straight through I3 — a second SELECT-only policy grants exactly one thing: *a user may see their own membership rows.* Three tests keep it narrow: it returns nothing for another user, nothing for an unidentified caller, and permits no UPDATE.

---

## Verified live

```
GET  /auth/me                     401  Not authenticated
POST /auth/register               201  {"status":"check_your_email"}
POST /auth/register (duplicate)   201  identical response
POST /auth/login (correct)        200  session issued, HttpOnly cookie set
POST /auth/login (wrong pw)       401  "Invalid email or password"
POST /auth/login (unknown email)  401  byte-identical
GET  /auth/me (no workspace yet)  403  "No workspace membership"
```

---

## What does not exist

- **Workspace-switch teardown is a seam, not an implementation.** Doc 06 §2.1 requires agent sessions torn down and scope-keyed caches invalidated on switch. Neither exists yet — agents are M12, caching M6/M8. The call site exists so a switch cannot ship without teardown being wired.
- **`require_executive_surface` has nothing to guard yet.** The dependency is written and tested; the Chief of Staff surface arrives in M9.
- **Email verification and domain verification are M3.** Registration returns `check_your_email`; nothing is sent. `workspace.domain_verified_at` and the partial unique index exist so a second domain claim cannot land while M3 is built.
- **Contributor's restricted L3 subset is flagged, not defined.** `contributor_restricted` is carried on `ScopedSession` and asserted, but *which* department data it excludes is `D5` in `DECISIONS-REQUIRED.md` — doc 06 §11.5 lists it as genuinely open, and it decides what M4's acceptance test asserts.

---

## How to validate

```powershell
.\scripts\verify.ps1
```

To see the isolation suite specifically:

```powershell
cd services\api; .\.venv\Scripts\python.exe -m pytest tests\test_tenant_isolation.py tests\test_auth_flow.py -v
```

Doc 07 M1 also says *"attempt a workspace switch and confirm session teardown"* — `test_switching_workspace_changes_visibility_immediately` does that at the database level, on one pooled connection.

**The most valuable thing you can do here is add a red-team case.** The suite is meant to be attacked; if you can think of a leak it does not attempt, that gap is worth more than another passing test.

---

## Invariants

| | Status |
|---|---|
| **I2** identity session-bound | Enforced — `ScopedSession` only, guarded against the source |
| **I3** filter before search | Enforced for relational reads via RLS; vector path arrives in M5/M6 |
| **I5** caches keyed by scope | `cache_key()` built and tested; no cache consumes it yet |
| **I10** never a zero | Applied to readiness; dashboard states are M9 |

---

## Next

**M2 — landing integration, URL capture, Preview audit.** Its first task is the SSRF corpus, written before the crawler it guards: `127.0.0.1`, `169.254.169.254`, `[::1]`, private ranges, `file://`, DNS rebinding, redirect-to-private, oversized bodies, slowloris. Doc 06 §1.2 also requires that no metered API is reachable from an unauthenticated path.
