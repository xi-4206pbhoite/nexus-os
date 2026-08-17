# 0008 — Neon serverless Postgres is the primary database

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decider:** the user, who provisioned the instance and supplied its credentials
- **Relates to:** [0001](0001-native-stack-no-docker.md),
  [0004](0004-pgvector-required-from-m5-not-m0.md),
  [0006](0006-pgvector-via-official-docker-image.md),
  [0007](0007-docker-engine-in-wsl-not-docker-desktop.md)

## Context

M5 made pgvector a hard requirement (ADR 0004), which the native Windows cluster
of ADR 0001 cannot satisfy — the binaries ZIP ships no extension and building one
needs a toolchain we deliberately avoided. ADR 0006 and 0007 answered that with
pgvector in a container, and that works.

But the user's stated direction was always a real server: *"in future we will
shift to actual postgres server."* Carrying two backends means every
database-touching decision gets made twice and verified once.

## Decision

**Neon serverless Postgres is the database the application is developed and
tested against.** The container of ADR 0006/0007 is retained as an offline
fallback, not as a parallel target.

Neon runs PostgreSQL 18.4 with `vector` 0.8.6 available, so migration 0007's hard
requirement is met without a build step.

## The part that mattered

Neon's provisioned role, `neondb_owner`, has **`rolbypassrls = true`**.

Connecting the application as that role would have left every RLS policy from
migration 0002 onward inert. The isolation suite would have kept passing —
`test_app_role_cannot_bypass_rls` is the only test that would have caught it, and
it is the first assertion in the file for exactly this reason. Every other test
in M1 asserts *behaviour under* a policy, and a bypassed policy produces the same
answers right up to the point where two tenants share a table.

So the application does not connect as `neondb_owner`. `db/bootstrap.sql` creates
`nexus_app` and verifies both `rolsuper` and `rolbypassrls` are false, raising if
either is not. On Neon that verification is doing real work: `ALTER ROLE ...
NOSUPERUSER NOBYPASSRLS` is *rejected* there — only a superuser may change those
attributes — so the script tolerates the failure and then proves the outcome
independently rather than assuming the statement did anything. A managed provider
that defaulted new roles to `bypassrls` would fail the bootstrap instead of
silently disabling tenant isolation.

`nexus_app` owns every table, which is what makes `FORCE ROW LEVEL SECURITY`
settable by the migrations. It does **not** own the schema; `GRANT USAGE, CREATE
ON SCHEMA public` is sufficient, and an earlier note in this repo claiming
otherwise was wrong.

## Consequences

- `.env` holds only `nexus_app`'s credentials. The `neondb_owner` password is not
  in the repo, not in `.env`, and not in any script.
- **The `neondb_owner` password was pasted into a chat transcript and should be
  rotated in the Neon console.** `nexus_app`'s password was generated locally and
  never transmitted.
- The DSN uses the **direct** host, not the pooler. `app/db.py` detects
  `-pooler` in the URL and switches to `NullPool` with prepared statements
  disabled, because PgBouncer's transaction mode breaks asyncpg's statement
  cache. Direct is correct for a long-lived server process; the pooler branch
  exists for the serverless deployment target.
- TLS spelling differs by driver: `.env` carries asyncpg's `ssl=require`;
  `tests/dburl.py` rewrites it to libpq's `sslmode=require` for the synchronous
  suites. Each driver rejects the other's spelling outright.
- **The suite takes ~5 minutes instead of ~8 seconds.** Every statement is a
  round trip to `us-east-2`. This is the real cost of the decision and it will be
  felt on every run. Keeping the container fallback is what makes it bearable.
- Version divergence: 18.4 on Neon, 17.11 locally. Nothing in the schema depends
  on the difference, and the tests now run against the version that will serve
  production rather than the one that happens to be installed.

## Revisit if

Latency makes the gate unusable in day-to-day work — the fix is running the
container by default and Neon before each milestone closes, not dropping either.
