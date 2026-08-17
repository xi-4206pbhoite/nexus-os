# NEXUS OS — working notes

## Shell — read this before writing any command for the user

The user runs **Windows PowerShell 5.1**. Commands are copied and pasted, so a
bash-ism is a broken command, not a style issue. This has already cost two
failed pastes.

| Never write | Write instead |
|---|---|
| `cd X && cmd` | `cd X; cmd` — or just `cmd`, since the prompt is already at the repo root |
| `curl -s URL` | `Invoke-RestMethod URL` (`curl` is an alias for `Invoke-WebRequest`; bash flags fail) |
| `VAR=x cmd` | `$env:VAR = 'x'; cmd` |
| `export VAR=x` | `$env:VAR = 'x'` |
| `rm -rf X` | `Remove-Item -Recurse -Force X` |
| A `.env` line in a shell block | Say "add this line to `.env`" — never in a runnable block |

**Prefer handing over a script over a command.** `scripts\verify.ps1`,
`scripts\ci.ps1`, `scripts\db-init.ps1` exist so the user never composes
anything. If a new instruction needs more than one line, it belongs in a script.

Two PowerShell 5.1 traps already hit in this repo:

- **Native stderr becomes a terminating error.** `alembic` and `psql` log INFO
  and NOTICE to stderr; with `$ErrorActionPreference='Stop'` that aborts a
  succeeding command. Set `Continue` around the call and branch on
  `$LASTEXITCODE`.
- `&&`, `||`, ternary and `??` do not exist.

## Process

Doc 07 is the build contract. **One milestone at a time; stop at the end of each
and wait for validation.** Every milestone ends with passing tests, a
`MILESTONE-N.md`, and an updated `TASKS.md`.

Where documents conflict: doc 07 > doc 06 > doc 05 > doc 04 > doc 03/01.
Conflicts settled by that rule are listed in `ARCHITECTURE.md` §0. Anything not
settled by it goes to `DECISIONS-REQUIRED.md` — **never invent a resolution.**

Every decision the user makes is recorded in `doc/adr/NNNN-title.md`.

## Invariants

The ten in doc 07 §2 are the reason the product exists. `ARCHITECTURE.md` §1
explains how the layering makes each structurally true rather than policy-true.
The two that shape almost every file:

- **I1** — every number is fetched or computed in code. `calculators/` is pure
  and contains no model.
- **I2 / I3** — `retrieval/` is the only path to data, takes a `ScopedSession`,
  and never accepts a `user_id`. The permission predicate is part of the query.

For anything touching permissions or grounding, **write the test that proves the
invariant before the feature it guards** (doc 07 §5.3).

## Local stack (ADR 0001 native; ADR 0006/0007 Docker for the database)

**Docker lives inside WSL2 Ubuntu, not on the Windows PATH** (ADR 0007). Never
write a bare `docker …` command — route it through `scripts/lib/docker.ps1`:
`Invoke-Docker` (prints, returns exit code), `Get-DockerOutput` (returns lines),
`Get-DockerContainerHealth`. The daemon does not survive a WSL restart;
`Start-DockerDaemon` handles that.

`winget` is unusable on this machine: Delivery Optimization hangs at 0 bytes
without erroring (three occurrences). Use a direct download and **verify the
Authenticode signature before running an installer** — one 629 MB download
matched Content-Length exactly and still failed with `HashMismatch`.

## Native fallback (ADR 0001)

```
PostgreSQL 17.11   D:\PostgreSQL         loopback only, no service, no admin
  superuser pw     D:\PostgreSQL\superuser.pw
  app role         nexus_app  NOSUPERUSER NOBYPASSRLS   <- load-bearing for RLS
object storage     .storage\              filesystem driver, HMAC-signed URLs
email              .mail\                 .eml files
embeddings         local multilingual-e5-large, 1024d (ADR 0003)
```

`nexus_app` must never be superuser or `BYPASSRLS`: M1's tenant isolation rests
on row-level security, which both silently bypass. Connecting as `postgres`
would make every isolation test pass while proving nothing.

**pgvector 0.8.6 is installed** via the `pgvector/pgvector:pg17` container
(ADR 0006/0007) and reported at every `/health/ready` call. The container's
`nexus_app` role is `NOSUPERUSER NOBYPASSRLS` — the official image makes
`POSTGRES_USER` a superuser, which would bypass RLS entirely, so the app never
connects as it.

## Commands

```powershell
.\scripts\setup.ps1      # one-time: venv, npm, .env
.\scripts\pg-local.ps1 -Action start|stop|status
.\scripts\db-init.ps1 -SuperPassword (Get-Content D:\PostgreSQL\superuser.pw)
.\scripts\ci.ps1         # the gate: ruff, ruff format, mypy --strict, pytest, tsc, lint, build
.\scripts\verify.ps1     # gate + health probes, for milestone validation
```

API: `cd services\api; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`
Web: `npm run dev --prefix apps\web`

## Content rule

The product sells on *never invent a number*. The landing page and every mock is
held to it too: no invented customers, logos, testimonials or results. Product
mocks carry a visible `Illustrative` tag.
