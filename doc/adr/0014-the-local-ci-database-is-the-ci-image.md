# ADR 0014 — The local gate builds its own database from the CI image

**Status** Accepted
**Date** 2026-09-03
**Decided by** Phase 0, forced by three measured facts about this machine.

## Context

ADR 0013 makes a database a precondition for running the suite. That raises the
question of *which* database a local `.\scripts\ci.ps1` should use. Three
candidates existed, and each failed for a different reason.

**The developer database in `.env` — Neon (ADR 0008).** It works, and the suite
runs against it. But its schema is **five migrations ahead of the repository**:
`alembic_version` reads `0014` while the migrations on disk head at `0009`, and
it holds `company_brain`, `question` and `question_choice`, which no migration
here creates. Its `ck_document_status` already includes `'superseded'` — the
value Phase 1's migration 0010 is scheduled to add, and which
`BUILD-STATUS.md` §5.2 records as *missing and causing a raise*. So a local run
against it proves something other than what the repository contains, in both
directions: a bug the repo still has can pass, and a fix the repo has made can
fail. Nothing in git produced that schema and no other branch or worktree holds
it.

**The native PostgreSQL 17.11 cluster (ADR 0001).** Starts fine, no admin
rights needed — and has no pgvector. `db/bootstrap.sql` fails on its first
statement: *extension "vector" is not available*. That absence is the whole
reason ADR 0006 exists.

**The `docker compose` service `db`.** Right image, but `db-docker.ps1` rewrites
`.env`, which would repoint the developer's configuration as a side effect of
running the gate. It also publishes `127.0.0.1:5432:5432`, which does not work
from Windows — see below.

## Decision

**`scripts\db-ci.ps1` builds a throwaway database the way
`.github/workflows/ci.yml` does, and sets `$env:NEXUS_DATABASE_URL` for that
shell only.** It never writes `.env`.

- the same image CI uses, `pgvector/pgvector:pg17`
- no volume, container recreated every run, so the schema is only ever what the
  migrations produce
- `db/bootstrap.sql`, mounted from `db\` rather than copied, so local and CI
  provably run the same file — extensions, and `nexus_app` as
  `NOSUPERUSER NOBYPASSRLS`. The image makes `POSTGRES_USER` a superuser, and a
  superuser ignores every policy in migration 0002 while the isolation suite
  passes
- `alembic upgrade head`, `downgrade base`, `upgrade head`
- port **55432**, so it cannot collide with the native cluster or with
  `docker compose up -d db`

## Three environment facts this had to work around

Each cost a debugging cycle, and each is invisible in the failure it produces.

**A port published to `127.0.0.1` inside WSL is unreachable from Windows.**
Docker runs inside WSL2 (ADR 0007), so `-p 127.0.0.1:55432:5432` binds the WSL
VM's loopback and Windows gets `connection refused` — while `docker exec` and
anything else inside WSL connects happily, so the bootstrap succeeds and only the
suite fails. Published to the VM's `0.0.0.0`, WSL2's localhost forwarding relays
`127.0.0.1:55432` from Windows. Measured both ways. WSL2 networking is NAT, so
this reaches the host and not the LAN. **`docker-compose.yml` has the same
problem** for anything running on Windows.

**WSL2 shuts a distribution down when idle, taking the daemon and every
container with it.** A suite run died 90 seconds in with `connection refused` on
every remaining database test; `wsl -l --running` reported no running
distributions and the container was `Exited (0)` with a fast-shutdown request in
its log. Nothing in the repository was wrong — the database had evaporated
mid-run. `db-ci.ps1` holds the distribution open with a sleeping process for the
duration, recording its PID so a second run does not leak one, and gives the
container `--restart unless-stopped` so a daemon restart brings it back.

**`pg_ctl start` hangs when its output is piped in PowerShell.** The `postgres`
it spawns inherits the pipeline's stdout handle, so the pipe never closes.
`Start-Process` with file redirection instead. This is in the script's history
rather than its final form, since the native cluster path was dropped, but it is
the same trap `scripts/lib/docker.ps1` documents for `Invoke-Docker`.

A fourth was self-inflicted and worth recording because the repo has hit it
before: a PowerShell function that both emits its output and returns a value
returns *both*, so `$status = Invoke-Native ...` came back as an array of log
lines with the exit code appended — and `$status -ne 0` on an array is a filtered
array, which is truthy. A running cluster was reported as stopped. `Write-Host`
for anything a caller is not meant to capture.

## Why not simply reset the Neon database

Because it is not mine to reset, and because the drift is evidence. Whatever
applied `0010`–`0014` also wrote schema the repository will need — the
`superseded` status and the `review_state` vocabulary are both scheduled work in
Phase 1, and `company_brain` and `question` are Phase 12/13. Dropping it silently
would destroy the only surviving trace of five migrations that exist nowhere in
git. Recorded in `DECISIONS-REQUIRED.md` for Parul.

## What this does not settle

- **Two local database paths now exist**: `db-docker.ps1` (persistent, writes
  `.env`, for running the app) and `db-ci.ps1` (throwaway, writes nothing, for
  running the gate). They are different jobs, but the overlap is worth revisiting
  once the Neon drift is resolved.
- **`db-ci.ps1` requires Docker in WSL.** On a machine without it there is no
  local way to run the gate, because the native cluster cannot supply pgvector.
- **The keepalive is a workaround for a WSL default**, not a fix. Setting
  `vmIdleTimeout` in `.wslconfig` would be the real answer, and that is a change
  to Parul's machine configuration rather than to this repository.
