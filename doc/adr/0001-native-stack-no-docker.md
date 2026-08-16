# ADR 0001 — Run the stack natively; no Docker Compose

**Status:** Accepted · 16 August 2026
**Decider:** Parul Bhoite
**Supersedes:** doc 07 §3 (object storage) and §6 M0 (`docker compose up` as the acceptance criterion)

## Context

Doc 07 §3 specifies PostgreSQL + pgvector and S3-compatible object storage, and M0's acceptance is *"`docker compose up` gives a running web and API"*. Docker is not installed on the development machine and Docker Desktop is not present.

Offered: install Docker Desktop, run natively, or pause M0. **Decision: run natively.**

## Decision

No Compose file. Each infrastructure dependency is replaced by a driver behind an interface, so the production shape is preserved and the local shape is free and installation-light.

| Dependency | Doc 07 §3 | Local substitute | Interface |
|---|---|---|---|
| PostgreSQL + pgvector | Compose service | **Free hosted instance** (Supabase or Neon free tier) | plain `DATABASE_URL` |
| Object storage | S3-compatible, signed URLs | Local filesystem under `.storage/` | `ObjectStore` — `FilesystemObjectStore` \| `S3ObjectStore` |
| Email (M3 verification) | not specified | Written to `.mail/` as `.eml` | `Mailer` — `FileMailer` \| SMTP driver |

**Postgres is hosted rather than local** because pgvector has no official Windows binary and building it requires MSVC toolchain setup — friction disproportionate to the benefit. Doc 03 §9 already recommends Supabase for speed to MVP, so this is spec-aligned rather than a workaround. Both candidate free tiers support `CREATE EXTENSION vector`.

**Signed URLs are still modelled.** `FilesystemObjectStore` issues short-lived HMAC-signed local URLs, so the calling code is identical to the S3 path and swapping drivers changes no application logic. Without this the signed-URL requirement would silently not exist until deployment.

## Consequences

- **M0's acceptance criterion changes** from `docker compose up` to: `make dev` (or the two documented commands) starts web and API, both `/health/ready` endpoints pass, CI is green.
- **The host Python version now matters.** Containerising would have pinned 3.12; running natively means the machine's 3.10.11 is what executes. See ADR 0004.
- **A `DATABASE_URL` for a pgvector-enabled instance is required before any migration runs.** This is the single outstanding blocker on M0.
- Adds a small amount of code (two driver implementations) that Compose would have made unnecessary. Both are thin and both are things a production deployment needs anyway in their S3/SMTP form.
- Onboarding a second developer is harder — no single command reproduces the environment. Acceptable at one developer; revisit if that changes.

## Revisit when

Docker becomes available, or a second developer joins, or we deploy — at which point the Compose file is written from the driver interfaces already in place.
