# NEXUS OS

An AI business operating system: seven AI directors reading one shared **Company
Brain**, for businesses in Oman and the wider GCC that cannot afford a full
executive team.

Every competing tool answers *"what happened?"*. NEXUS answers *"what should I do
about it?"* — and then does it. Every number it shows is fetched from a source
system or computed by deterministic Python. **The model interprets and phrases;
it never produces a number.**

---

## Start here

| Read this | For |
|---|---|
| **[`VISION-AND-PLAN.md`](VISION-AND-PLAN.md)** | The vision, the ten invariants, and the nine-phase build plan with an acceptance test per phase. **The build contract** |
| **[`ARCHITECTURE-HLD.md`](ARCHITECTURE-HLD.md)** | System shape, the trust and permission model, the untrusted-content boundary, deployment topology |
| **[`ARCHITECTURE-LLD.md`](ARCHITECTURE-LLD.md)** | Modules, schema and RLS policies, endpoint contracts, sequences, failure paths, config |
| **[`BUILD-STATUS.md`](BUILD-STATUS.md)** | What is actually built, verified against the code, with a prioritised work list |
| **[`DECISIONS-REQUIRED.md`](DECISIONS-REQUIRED.md)** | Fifteen open decisions; six of them block current work |
| **[`AUDIT-FINDINGS.md`](AUDIT-FINDINGS.md)** | What four audits found, and what was done about each |
| **[`USAGE.md`](USAGE.md)** | Running it locally |
| **[`doc/00-README.md`](doc/00-README.md)** | The eight specification documents |
| **[`CLAUDE.md`](CLAUDE.md)** | Working conventions — PowerShell rules, database facts, invariants |

---

## Status

**~32% complete.** The foundation is strong: forced row-level security proved
against Neon, an SSRF guard with 89 test cases, role→scope as data, and honest
optional-dependency boundaries for the language model and the embedder. Almost
none of the product surface is reachable by a user yet.

Four of the ten invariants are currently proved. The next four days of work
(Phase 1) make existing claims true rather than adding features — see
`VISION-AND-PLAN.md` §6.

---

## Stack

Next.js 14 (App Router, TypeScript, Tailwind) · Python 3.12 + FastAPI + Pydantic v2 ·
PostgreSQL 18.4 + pgvector 0.8.6 on Neon, row-level security forced ·
Alembic · APScheduler · Claude Agent SDK (planned)

The language model and the embedding model are **optional extras**. No API key and
no local model are supported states, reported honestly at `/health/ready` — not
degraded ones, and never filled in with fabricated output.

---

## Running it

```powershell
.\scripts\setup.ps1      # one-time: venv, npm, .env
.\scripts\api.ps1        # the API; add -Reload to watch services\api\app
.\scripts\ci.ps1         # the gate: parse, ruff, mypy --strict, pytest, tsc, lint, build
.\scripts\verify.ps1     # gate plus health probes
```

Web: `npm run dev --prefix apps\web` — and stop it before running `ci.ps1`, since
both write `apps\web\.next`.

Full instructions, including database setup, are in [`USAGE.md`](USAGE.md).
