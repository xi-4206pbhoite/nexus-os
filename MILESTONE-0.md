# Milestone 0 — Foundation

**Status:** complete except one task — **ready for your validation**
**Date:** 16 August 2026 · 10 commits on `main`

Doc 07 §5.2 asks each milestone to describe what exists **and what does not**.

---

## Verified working

Everything below was executed, not just written.

### Gate — `scripts/ci.ps1` green, all 7 checks

```
api: ruff check    PASS      web: tsc      PASS
api: ruff format   PASS      web: lint     PASS
api: mypy strict   PASS      web: build    PASS
api: pytest        PASS  (41 tests)
CI GREEN
```

`mypy --strict` clean across 8 source files, from M0 as doc 07 §3 requires.

### API — runs

```
GET /health        200  {"status":"ok","service":"nexus-api"}
GET /health/ready  503  {"status":"not_ready","env":"local","checks":[
                          {"name":"database","state":"unconfigured",
                           "detail":"NEXUS_DATABASE_URL is not set — see .env.example"},
                          {"name":"object_storage","state":"ok",
                           "detail":"filesystem:.storage"}]}
```

Liveness never touches a dependency, so a database outage cannot cause a restart loop. Readiness reports each dependency separately and **never claims `ok` for something merely unconfigured** — I10 applied to our own operations surface. The database probe asserts **pgvector is present**, not merely that Postgres answers, and on failure returns the exception *type* only, because an asyncpg error message can contain the DSN.

### Web — runs, and honestly reports the chain

```
GET /api/health  →  {"status":"ok","service":"nexus-web",
                     "api":"not_ready","apiDetail":"api returned 503"}
```

API reachability is a separate field, so "web is down" and "web is up but cannot reach the API" stay distinguishable. Landing page still statically prerendered after the move to `apps/web` (157 kB first load).

### Migrations — wired

`alembic heads` → `0001 (head)`. Without a URL it fails with `NEXUS_DATABASE_URL is not set. Copy .env.example to .env and fill it in.` — actionable, not a stack trace. No credential in `alembic.ini`.

### Tests — 41 passing

| Area | Cases | What they prove |
|---|---|---|
| Logging | 14 | Secret-shaped keys masked; **customer-content keys raise rather than log**; identifiers still loggable |
| Storage | 12 | Round-trip; workspace-prefixed keys; traversal rejected; signature bound to its key; expiry; tampering |
| Health | 5 | Liveness independent of dependencies; readiness honest; request-id propagation |
| Misc | 10 | Config, mail |

Two are worth calling out:

- **`test_customer_content_keys_raise_rather_than_log`** — masking is not enough. A masked field still tells an operator the content existed and invites someone to "temporarily" unmask it. Customer text belongs in `generation.input_snapshot`, which is scope-tagged and retention-managed, not in an unbounded log stream.
- **`test_signature_is_bound_to_the_key`** — a signed URL for one workspace's object must not open another's. Closing this at the storage layer as well as the query layer is defence in depth for the cross-tenant isolation M1 will enforce.

---

## What does not exist

### Migration 0001 has never been applied ⛔

No `NEXUS_DATABASE_URL`. Per ADR 0001 this needs a free hosted pgvector-enabled Postgres (Supabase or Neon). Until it runs:

- `/health/ready` returns `unconfigured` for the database and the service is correctly `not_ready`
- The pgvector guard in the migration is unproven against a real server

**This is the only thing standing between M0 and sign-off.**

### Deliberately deferred, not forgotten

- **Tenancy tables are not in migration 0001.** `tenant`, `user`, `workspace`, `membership` move to M1, where they are designed together with row-level security and the role→scope mapping. Creating them here would produce a migration M1 immediately rewrites.
- **S3 and SMTP drivers exist as interfaces only.** Filesystem and file drivers are the implementations. Both production drivers are small once there is somewhere to deploy.
- **No pre-commit secret hook.** gitleaks is in the workflow, but ADR 0002 means no remote executes it; `.gitignore` plus review is the control for now.
- **`app/db.py` exposes only `_unscoped_session`**, named to discourage use. From M1 every customer-data read goes through `retrieval/`, which requires a `ScopedSession` and applies the permission predicate in the query (I2, I3). A freely-available session is exactly the bypass those invariants exist to prevent.

---

## To close M0

Put a pgvector Postgres URL in `.env` as `NEXUS_DATABASE_URL`, then:

```
cd services\api
.\.venv\Scripts\alembic.exe upgrade head
```

`/health/ready` should then return `200` with `database: ok — pgvector present`.

---

## Invariants

M0 is scaffolding; none are enforced yet. Three are pre-staged:

- **I10** — readiness treats `unconfigured` as a named state, never a silent success
- **Doc 07 §7** (no customer content in logs) — enforced by a processor that raises, with tests
- **I2/I3** — the only database accessor is deliberately named `_unscoped_session` and documented as infrastructure-only, so the scoped path M1 builds is the obvious one
