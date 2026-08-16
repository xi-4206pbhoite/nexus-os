# ADR 0006 — pgvector via the official Docker image

**Status:** Accepted · 17 August 2026
**Decider:** Parul Bhoite ("install Docker Desktop and use the official pgvector image")
**Supersedes:** [ADR 0004](0004-pgvector-required-from-m5-not-m0.md) · partially reverses [ADR 0001](0001-native-stack-no-docker.md)

## Context

ADR 0004 deferred pgvector to M5 because no pgvector-capable Postgres was reachable: no Docker, no WSL, no MSVC toolchain, and the only prebuilt Windows binaries came from an unvetted third party. That deferral has now run out — M5's first migration hard-requires the extension.

Three options were offered. Docker Desktop with `pgvector/pgvector` was chosen, which is also the option doc 07 §3 specifies in the first place.

## Decision

**`pgvector/pgvector:pg17` via Docker Compose becomes the database for local development.** The native cluster from ADR 0001 stays installed and working as a fallback; `.env` decides which is in use, and nothing in the application changes between them.

Compose covers the database only. Object storage and mail remain the filesystem drivers from ADR 0001 — they work, they are tested, and containerising them would add moving parts to replace something that is not a problem.

### The detail that makes this non-trivial

**The official Postgres image creates `POSTGRES_USER` as a superuser, and a superuser bypasses row-level security unconditionally.** An application connecting as it would sail straight through every policy in migration 0002, and the entire M1 isolation suite would pass while proving nothing — the exact failure `db-init.ps1` was written to avoid on the native cluster.

So `docker/postgres/init/01-app-role.sh` creates `nexus_app` as `NOSUPERUSER NOBYPASSRLS`, and the superuser exists only to own extensions and run migrations. The isolation suite's first assertion — that the app role cannot bypass RLS — is what keeps this honest across both backends.

The healthcheck asserts **the extension is present**, not merely that Postgres is accepting connections. `pg_isready` returns true before the init scripts finish, so a naive healthcheck would report ready while `vector` did not yet exist.

## Consequences

- **M5 is unblocked.** Its migration can hard-require `vector`, and `/health/ready` will report `pgvector: ok` for the first time.
- **This is a fresh database.** The Docker volume starts empty, so migrations re-run and the local test data from M0–M4 does not carry over. That data was only ever fixtures.
- **Docker Desktop needs prerequisites this session cannot install.** Windows Home requires WSL2, which is not installed; `wsl --install` and the Docker installer both need elevation, and WSL needs a reboot. Two elevated commands and a restart, listed in `MILESTONE-4.md` and the README.
- **Both backends must keep working.** `.env` selects one; `scripts/verify.ps1` reports which is live. If they diverge, the native path is the one to drop — Docker is what doc 07 §3 specifies.
- ADR 0001's driver-behind-an-interface pattern is vindicated rather than undone: nothing in the application changed to switch database backends.

## Revisit

If Docker proves unreliable on this machine, or when a deployment target is chosen — at which point the Compose file is the starting point for it rather than a local-only convenience.
