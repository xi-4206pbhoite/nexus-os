# Milestone 0 — Foundation

**Status:** partially complete — **not ready for sign-off**
**Date:** 16 August 2026 · 7 commits on `main`

Doc 07 §5.2 asks each milestone to describe what exists **and what does not**. The second list is the longer one here.

---

## What exists

### Repository and process
- `git init` on `main`; `.gitignore` excludes `.env` and the ADR 0001 local substitutes (`.storage/`, `.mail/`, `models/`) which hold customer content; `.gitattributes` normalises to LF
- Restructured to the doc 07 §4 layout — the landing page moved `nexus_os_application/web` → `apps/web`
- ADRs 0001–0003 recording your three decisions (doc 07 §1)
- `ARCHITECTURE.md`, `TASKS.md`, `DECISIONS-REQUIRED.md`

### Web — verified running
- Landing page builds and serves; **still statically prerendered** after the move (157 kB first load)
- `/api/health` reports web liveness plus API reachability as a **separate field**, so "web is down" and "web is up but cannot reach the API" stay distinguishable
- `tsc --noEmit`, `next lint`, `next build` all pass

### API — written, **not yet executed** (see below)
- FastAPI app with request-id middleware
- `config.py` — pydantic-settings, no usable default for any secret; a missing one raises at startup rather than running on a placeholder
- `logging.py` — structlog JSON; secret-shaped keys masked; **keys carrying customer content raise rather than log**
- `health.py` — liveness never touches a dependency; readiness reports each dependency separately and never claims `ok` for something merely unconfigured
- `storage.py` — `ObjectStore` interface + filesystem driver issuing **expiring HMAC-signed URLs**
- `mail.py` — `Mailer` interface + file driver writing `.eml`
- Tests written: logging redaction (14 cases), health behaviour (5), storage contract (12 including traversal, cross-key signature reuse, expiry, tampering)

### CI
- `.github/workflows/ci.yml` — ruff · ruff format · mypy --strict · pytest · tsc · next lint · next build · gitleaks
- `scripts/ci.ps1` runs the identical gate locally, which is the real gate until a remote exists (ADR 0002)
- `scripts/setup.ps1` replaces `docker compose up` as the way the stack is prepared

---

## What does not exist

### The API has never run
**Python 3.12 is not installed.** The machine has 3.10.11, and `config.py` uses `StrEnum` (3.11+), so the service cannot start. I attempted a `winget` install; it stalled for several minutes with nothing written — almost certainly waiting on a hidden dialog in a non-interactive session — so I terminated it and confirmed no partial install was left behind.

**Consequence:** every statement above about the API is "written and type-annotated", not "verified". No test in `services/api/tests/` has been executed. Treat that section as unvalidated until 3.12 lands.

### No database
No `NEXUS_DATABASE_URL`. Per ADR 0001 this needs a free hosted pgvector-enabled Postgres (Supabase or Neon). Blocked as a result:

- Task 0.5 — alembic and migration 0001 (`vector` + `pgcrypto` extensions, `tenant`, `user`, `workspace`, `membership`)
- The real database probe in `/health/ready`, which currently reports `degraded — probe not yet implemented` rather than pretending to be `ok`

### Deliberately deferred
- S3 and SMTP drivers exist as interfaces only — the filesystem and file drivers are the implementations. Correct for now; both production drivers are small once there is somewhere to deploy
- No secret-scanning pre-commit hook yet; gitleaks runs in the workflow but no remote executes it

---

## Amended acceptance criterion

Doc 07 M0 says *"`docker compose up` gives a running web and API; CI is green."* ADR 0001 removed Compose, so:

> `scripts/setup.ps1` prepares the stack from a clean clone · API and web both start · `/health` returns ok and `/health/ready` reports every dependency honestly · `scripts/ci.ps1` is green.

**Currently:** web ✅ · API ❌ (no Python 3.12) · CI partial (web ✅, API unrun).

---

## To finish M0

1. **Install Python 3.12** — `winget install --id Python.Python.3.12 --scope user` in an interactive terminal, or the python.org installer
2. **Provide a pgvector Postgres URL** — Supabase or Neon free tier, into `.env` as `NEXUS_DATABASE_URL`
3. Then I run `scripts/setup.ps1`, execute the API test suite, write migration 0001, wire the real database probe, and bring `scripts/ci.ps1` fully green

---

## Invariants

None are enforced yet — M0 is scaffolding. Two are pre-staged:

- **I10** (never a zero, never a blank) is already applied to readiness: `unconfigured` is a named state, not a silent success
- Doc 07 §7's *no customer content in logs* is enforced by a processor that raises, with tests
