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

## Database — Neon is the target (ADR 0008)

```
Neon serverless Postgres 18.4    pgvector 0.8.6, direct host (not the pooler)
  app role   nexus_app           NOSUPERUSER NOBYPASSRLS  <- load-bearing for RLS
  .env holds nexus_app only      neondb_owner creds are not in the repo
```

**`neondb_owner` has `rolbypassrls = true`.** Connecting as it would leave every
RLS policy inert while the whole isolation suite kept passing. The app connects
as `nexus_app`; `db/bootstrap.sql` *verifies* both flags are false and raises if
not, because Neon rejects `ALTER ROLE … NOSUPERUSER` outright. Tolerate the
statement, prove the outcome — never assume the ALTER did anything.

`nexus_app` owns every table (that is what makes `FORCE ROW LEVEL SECURITY`
settable). It does **not** need to own the schema.

TLS spelling is per-driver: `.env` carries asyncpg's `ssl=require`;
`tests/dburl.py` rewrites it to libpq's `sslmode=require`. Each driver rejects
the other's spelling. Never add a second `_database_url()` to a test module —
import `database_url()` from `tests/dburl.py`.

The suite takes **~5 minutes** against Neon versus ~8 seconds locally; every
statement is a round trip to `us-east-2`. That is expected, not a hang.

## Local stack (ADR 0001 native; ADR 0006/0007 Docker for the offline fallback)

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
.\scripts\api.ps1        # the API; add -Reload to watch services\api\app
.\scripts\ci.ps1         # the gate: parse, ruff, mypy --strict, pytest, tsc, lint, build
.\scripts\smoke.ps1      # every endpoint, asserting refusals as well as successes
.\scripts\verify.ps1     # gate + health probes, for milestone validation
.\scripts\db-init.ps1 -SuperPassword (Get-Content D:\PostgreSQL\superuser.pw)
```

Web: `npm run dev --prefix apps\web`

**Stop the web dev server before running `ci.ps1`.** Both write `apps\web\.next`,
and a concurrent `next build` fails with `PageNotFoundError: Cannot find module
for page`. If the dev server itself starts 500ing with `Cannot find module
'./NNN.js'`, the cache is corrupt: stop it, delete `.next`, restart. The source is
fine - that is HMR, not a build error.

## The language model is optional (ADR 0011)

**No API key is a supported state, not a degraded one.** The application starts,
serves everything, and reports `language_model: unconfigured` on `/health/ready`.
To switch it on: set `NEXUS_ANTHROPIC_API_KEY`, then `pip install -e ".[ai]"` in
`services\api`.

Two rules the tests enforce:

- **Nothing outside `app/ai/` names the vendor.** `test_ai_boundary.py` asserts it,
  verified by planting a violating import and watching it fail. Depend on
  `app.ai.contracts.LlmProvider`.
- **Nothing invents content.** `UnavailableProvider` refuses when called;
  `ScriptedProvider` raises on an unscripted skill. There is no demo mode that
  returns plausible analysis - a fabricated recommendation destroys the product's
  central claim whether or not it is labelled, because the label stays on the
  screen and the screenshot does not.

`anthropic_api_key` deliberately bypasses `Settings.require()`. Every other secret
fails loudly when absent; this one must not.

## Known defects

`AUDIT-FINDINGS.md` records what four audits found and what was done about each.
Fourteen findings are open and scheduled. The three worth knowing before touching
auth or deployment: **argon2 blocks the event loop**, **`/auth/login` has no rate
limit** (both D14), and **`env` defaults to `local`** - so a missing `NEXUS_ENV`
in production serves `/docs` and sets `secure=False` on both cookies.

## Content rule

The product sells on *never invent a number*. The landing page and every mock is
held to it too: no invented customers, logos, testimonials or results. Product
mocks carry a visible `Illustrative` tag.
