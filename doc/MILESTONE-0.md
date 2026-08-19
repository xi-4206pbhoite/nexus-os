# Milestone 0 — Foundation

**Status:** ✅ complete — **ready for validation**
**Date:** 16 August 2026 · 13 commits on `main`

Doc 07 §5.2 asks each milestone to describe what exists **and what does not**.

---

## Acceptance

Doc 07 M0 says *"`docker compose up` gives a running web and API; CI is green."* [ADR 0001](doc/adr/0001-native-stack-no-docker.md) removed Compose, so the amended criterion is:

> `scripts/setup.ps1` prepares the stack from a clean clone · API and web both start · `/health` returns ok and `/health/ready` reports every dependency honestly · `scripts/ci.ps1` is green.

**All four met.**

```
=== api: ruff check ===   PASS      === web: tsc ===    PASS
=== api: ruff format ===  PASS      === web: lint ===   PASS
=== api: mypy strict ===  PASS      === web: build ===  PASS
=== api: pytest ===       PASS  (46 tests)
CI GREEN
```

---

## Running stack

**PostgreSQL 17.11**, self-contained under `D:\PostgreSQL`, loopback only, no Windows service, no admin rights. Removable by deleting one directory.

```
alembic_version : 0001
extensions      : pgcrypto, plpgsql
nexus_app role  : rolsuper=f  rolbypassrls=f  rolcreatedb=f
```

That role configuration is load-bearing, not hygiene. **M1's tenant isolation rests on row-level security, and RLS is silently bypassed by superuser and `BYPASSRLS` roles.** Had the app connected as `postgres` — the obvious thing on a local dev database — every cross-tenant isolation test in M1 would have passed while proving nothing.

**API**

```
GET /health        200  {"status":"ok","service":"nexus-api"}
GET /health/ready  200  database       ok            connected              required_now: true
                        pgvector       unconfigured  not available on this  required_now: false
                                                     server — required
                                                     from M5 (retrieval)
                        object_storage ok            filesystem:.storage    required_now: true
```

**Web**

```
GET /api/health    200  {"status":"ok","service":"nexus-web","api":"ok","apiDetail":null}
```

Landing page still statically prerendered (157 kB first load); `/api/health` is the only dynamic route.

---

## What exists

| Area | Detail |
|---|---|
| **Repo** | `main`, doc 07 §4 layout, landing page moved to `apps/web`, `.env` and local state gitignored |
| **API** | FastAPI, request-id middleware, pydantic-settings with no usable default for any secret |
| **Logging** | structlog JSON; secret-shaped keys masked; **customer-content keys raise rather than log** |
| **Health** | Liveness touches nothing; readiness reports each dependency separately with required/advisory distinction |
| **Storage** | `ObjectStore` interface + filesystem driver issuing **expiring HMAC-signed URLs** |
| **Mail** | `Mailer` interface + file driver writing `.eml` |
| **Migrations** | Alembic wired; `0001` applied; fails with an actionable message when unconfigured |
| **Scripts** | `setup.ps1`, `pg-local.ps1`, `db-init.ps1` (idempotent), `ci.ps1` |
| **CI** | Workflow committed; `ci.ps1` is the live gate until a remote exists (ADR 0002) |
| **ADRs** | 0001 native stack · 0002 git local · 0003 local embeddings · 0004 pgvector from M5 |

### Tests — 46

| Area | Cases | What they prove |
|---|---|---|
| Logging | 14 | Secrets masked; **customer content raises rather than logs**; identifiers still loggable |
| Storage | 12 | Round-trip, workspace-prefixed keys, traversal rejected, signature bound to its key, expiry, tampering |
| Health | 8 | Liveness independent of dependencies; readiness honest; pgvector advisory; request-id propagation |
| Hermeticity | 3 | Suite ignores local `.env`; probes never write into the repo; secrets fail loudly |
| Config / mail | 9 | — |

**Three findings worth naming**, because each was a real defect rather than a passing test:

1. **The suite was reading my local `.env`.** The moment a real database was configured, health tests began failing locally while still passing in CI (which has no `.env`). A suite whose verdict depends on machine state cannot prove an invariant — and from M1 these tests are what prove tenant isolation. Fixed with a hermetic fixture plus `test_hermeticity.py` as a regression guard.
2. **`db-init.ps1` rotated the app password without updating `.env`.** A second run left a valid-looking `.env` that could not connect. Now it refuses to rotate a password `.env` depends on unless `-Rotate` is passed.
3. **PowerShell 5.1 wraps a native command's stderr in an ErrorRecord**, so `alembic`'s INFO logging aborted the migration step of a script that was otherwise succeeding. Both call sites now branch on the real exit code.

---

## What does not exist

### pgvector is not installed

The stock EnterpriseDB build ships 233 extensions; pgvector is not among them. Per [ADR 0004](doc/adr/0004-pgvector-required-from-m5-not-m0.md) this is **fine until M5** and is reported at every readiness call rather than being silently absent.

**It must be resolved before M5 starts.** Three options, none yet chosen:

1. Docker Desktop + the official `pgvector/pgvector` image — matches doc 07 §3 exactly
2. A hosted Postgres with pgvector — doc 03 §9 already recommends Supabase
3. Local build from official pgvector source with MSVC Build Tools

Community prebuilt Windows DLLs exist and were **deliberately not used** — loading an unsigned third-party binary into the database process should be an explicit decision, not a convenience taken mid-milestone.

### Deliberately deferred

- **Tenancy tables are not in migration 0001.** `tenant`, `user`, `workspace`, `membership` belong to M1, where they are designed together with RLS and the role→scope mapping.
- **S3 and SMTP drivers are interfaces only.** Filesystem and file drivers are the implementations.
- **No remote, so no hosted CI run.** `ci.ps1` runs the identical checks locally (ADR 0002).
- **`app/db.py` exposes only `_unscoped_session`**, named to discourage use. From M1 every customer-data read goes through `retrieval/`, which requires a `ScopedSession` and applies the permission predicate in the query (I2, I3).

---

## How to validate

One command, from `D:\Projects\NEXUS_OS`:

```powershell
.\scripts\verify.ps1
```

It runs the full gate and probes every health endpoint, printing each dependency and its state. Expect **ALL GREEN**.

Start the services first if the probes fail (each in its own terminal):

```powershell
cd services\api; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

```powershell
npm run dev --prefix apps\web
```

To see the honest degradation for yourself — stop the database, re-probe, restart:

```powershell
.\scripts\pg-local.ps1 -Action stop
.\scripts\verify.ps1 -SkipGate
.\scripts\pg-local.ps1 -Action start
```

Readiness should go **503** with `database: error`, while `/health` stays **200** — an outage must not look like a dead process.

---

## Invariants

M0 is scaffolding; none are enforced yet. Four are pre-staged:

- **I10** — `unconfigured` is a named state, never a silent success. Applied to our own ops surface before any dashboard tile.
- **Doc 07 §7** — no customer content in logs, enforced by a processor that raises.
- **I2 / I3** — the only database accessor is deliberately named `_unscoped_session`; the app role cannot bypass RLS.
- **I9** — nothing to audit yet, but `generation` is designed into the data model in `ARCHITECTURE.md` §6.

---

## Next

**M1 — tenancy, auth, roles.** Its first task is the cross-tenant and cross-workspace isolation suite, written *before* the code it guards (doc 07 §5.3).

**Decision needed around then:** `D5` in [DECISIONS-REQUIRED.md](DECISIONS-REQUIRED.md) — the Contributor L3 subset. Doc 06 §11.5 lists it as genuinely open, and it determines what M4's acceptance test actually asserts.
