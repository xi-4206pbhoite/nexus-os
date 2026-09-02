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

## The documents, and which one to trust

| Document | What it governs |
|---|---|
| `VISION-AND-PLAN.md` | **The build contract.** Vision, invariants, the nine phases and their acceptance tests |
| `doc/09-NEW-APPLICATION-FLOW.md` | **The new flow.** The nine-stage journey. Supersedes doc 06 §0 and doc 04 §5 |
| `doc/11-FLOW-DECISIONS.md` | **Every flow decision Parul has made**, and the four still open. Answers `doc/10` |
| `doc/12-IMPLEMENTATION-PLAN.md` | **The executable plan.** Twenty-two phases, each with an acceptance test. Supersedes `VISION-AND-PLAN.md` §6 |
| `ARCHITECTURE-HLD.md` | System shape, trust model, untrusted boundary, execution modes, deployment |
| `ARCHITECTURE-LLD.md` | Modules, schema, RLS, endpoint contracts, sequences, failure paths |
| `BUILD-STATUS.md` | Where the code actually stands, with the prioritised work list. Regenerated per phase |
| `DECISIONS-REQUIRED.md` | Open decisions, most of them external. **D23 blocks trusting any local run** |
| `AUDIT-FINDINGS.md` | What audits found and what was done about each |
| `doc/01`–`doc/08` | The specification. Read-only |
| `doc/adr/` | Every decision Parul has made |
| `doc/archive/` | Retired: `ARCHITECTURE.md`, `TASKS.md`, `MILESTONE-0…5.md`. Historical only |

## Process

`VISION-AND-PLAN.md` is the build contract. **One phase at a time; stop at the end
of each and wait for validation.**

**A phase is complete when its acceptance test has run green in CI against a real
Postgres, driven through the application rather than around it.** Not when the
code exists, and not when a unit test passes over a monkeypatched write. This rule
replaced the `MILESTONE-N.md` note, which produced six documents that agreed with
each other and disagreed with the database.

Where documents conflict: `VISION-AND-PLAN.md` (plan) > doc 07 §2/§8 (invariants,
out-of-scope) > doc 06 > doc 05 > doc 04 > doc 03/01. Conflicts settled by that
rule are listed in `ARCHITECTURE-HLD.md` §2. Anything not settled by it goes to
`DECISIONS-REQUIRED.md` — **never invent a resolution.**

Every decision the user makes is recorded in `doc/adr/NNNN-title.md`.

## Invariants

The ten in doc 07 §2 are the reason the product exists. `ARCHITECTURE-HLD.md` §3
explains how the layering makes each structurally true rather than policy-true;
`VISION-AND-PLAN.md` §3 tracks which are currently proved. **Four of ten are.**
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
import `database_url()` from `tests/dburl.py`. It resolves the URL **once, at
import**, because `conftest.py` pins `NEXUS_DATABASE_URL` to empty for
hermeticity — so a read at call time falls through to the `.env` fallback, which
exists here and never in CI, and the same code then reads Neon locally and
`None` in CI.

The suite takes **~5 minutes** against Neon versus ~25 seconds against the local
container; every statement is a round trip to `us-east-2`. That is expected, not
a hang.

**The Neon instance is five migrations ahead of this repository.**
`alembic_version` reads `0014`; the migrations on disk head at `0009`. It holds
`company_brain`, `question` and `question_choice`, which no migration here
creates, and its `ck_document_status` already permits `'superseded'` — the value
Phase 1's migration 0010 is scheduled to add. Nothing in git, on any branch, in
any stash or worktree produced that schema. So a run against it can pass a defect
the repository still has, and fail a fix it has made. **D23 in
`DECISIONS-REQUIRED.md`; nothing was reset.** Run the gate against
`scripts\db-ci.ps1` until that is answered.

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
.\scripts\db-ci.ps1      # the database the gate needs; -RunGate to run ci.ps1 after it
.\scripts\ci.ps1         # the gate: parse, ruff, mypy --strict, pytest, tsc, lint, build
.\scripts\smoke.ps1      # every endpoint, asserting refusals as well as successes
.\scripts\verify.ps1     # gate + health probes, for milestone validation
.\scripts\db-init.ps1 -SuperPassword (Get-Content D:\PostgreSQL\superuser.pw)
```

Web: `npm run dev --prefix apps\web`

**The gate needs a database, and refuses to run without one** (ADR 0013).
Ninety-four tests assert database behaviour; before Phase 0 they skipped and CI
reported green with row-level security never exercised. Now
`tests/test_ci_contract.py` fails when no database is configured, and
`conftest.py` fails the session naming every `requires_db` test that skipped.
`requires_db` is a real marker under `--strict-markers`; the skip decision lives
in exactly one place.

**Use `db-ci.ps1` for the gate, not the URL in `.env`** (ADR 0014). It builds a
throwaway database from the CI image and this repository's own `bootstrap.sql`
and migrations, on port 55432, and points that shell at it without touching
`.env`. `-Action down` removes it. Two reasons it exists: the native cluster has
no pgvector, and the Neon instance in `.env` is five migrations ahead of the
repository (see the Neon section above).

Three WSL traps it works around, each invisible in the failure it produces: a
port published to `127.0.0.1` **inside** WSL is unreachable from Windows, while
`docker exec` connects fine — so the bootstrap succeeds and only the suite fails;
WSL shuts the distribution down when idle, taking the database with it mid-run;
and `pg_ctl start` hangs when its output is piped, because the `postgres` it
spawns inherits the pipeline's stdout handle.

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

## Semantic search is optional too (ADR 0003 + the ADR 0011 pattern)

**No embedding model is a supported state.** `fastembed` and the ~2GB
`multilingual-e5-large` weights are an optional extra. Without them documents
still upload, parse, classify and reach the review queue; their chunks are stored
with a NULL embedding, which migration 0007's `ck_chunk_embedding_provenance`
permits, and `/health/ready` reports `embeddings: unconfigured`. To switch it on:
`pip install -e ".[embeddings]"` in `servicespi`.

Three rules the tests enforce:

- **Nothing outside `app/embeddings/` names the library.** Depend on
  `app.embeddings.contracts.Embedder`. `test_embedding_boundary.py` asserts it -
  and caught a prose mention of the *other* vendor in a docstring, so the same
  rule applies to comments.
- **Nothing fabricates a vector.** `DeterministicEmbedder` is hash-derived, is
  never returned by the registry, and no setting can select it. This is stricter
  than the LLM rule for a reason: a scripted provider refuses and fails loudly,
  whereas a fake embedding *ranks*. It produces confident citations beside a real
  answer with no visible symptom at all.
- **`embed_documents` and `embed_query` are separate, and not interchangeable.**
  E5 is trained with `passage:` and `query:` prefixes; omitting or swapping them
  does not raise, it just retrieves worse - indistinguishable from the product
  being mediocre.

**Retrieval must set `hnsw.iterative_scan` (ADR 0012).** Measured, not assumed: a
plain HNSW index with the permission predicate as an ordinary `WHERE` returns
**5% recall** at the selectivity of a Contributor reading their own rows. Raising
`ef_search` looks like the fix and is not - it rescues a department-sized filter
and leaves narrow ones broken. Partial indexes per scope are not needed.

The embedding pass runs **in the API process** on a 5-minute interval, which is
fine only while the model is absent by default. Once `[embeddings]` is installed
in production, ~2GB of weights are resident in the process serving requests and
it belongs in a separate worker.

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
