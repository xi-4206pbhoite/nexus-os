# ADR 0002 — Git initialised locally, no remote

**Status:** Accepted · 16 August 2026
**Decider:** Parul Bhoite

## Context

Doc 07 §5.5 requires small commits with clear messages, and per-milestone validation is far easier to review as diffs. `D:\Projects\NEXUS_OS` was not a git repository.

## Decision

`git init` at the repository root, default branch `main`, local only. No remote configured.

The first commit contains `/doc`, the three planning artifacts (`ARCHITECTURE.md`, `TASKS.md`, `DECISIONS-REQUIRED.md`), `.gitignore` and `.gitattributes` — the specification and the plan, before any code.

`.gitignore` excludes `.env` and every `.env.*` except `.env.example`, plus `.storage/`, `.mail/` and `/models/` — the local substitutes introduced by ADR 0001, which hold customer content and must never be committed.

## Consequences

- Work is not backed up off-machine. A disk failure loses the repository. Worth revisiting before the build gets long.
- CI (doc 07 §3 — *"type checking and linting must pass in CI from milestone 0"*) cannot run on a hosted runner without a remote. **Mitigation:** the CI definition is written and committed now, and a `make ci` target runs the identical checks locally, so the gate is real from M0 even though no hosted runner executes it. When a remote is added, the workflow already exists.
- Doc 07 §7's *"no secret in the repo"* is enforced by `.gitignore` plus a pre-commit secret scan added in M0.

## Revisit when

A remote is wanted — at which point `git remote add origin` and a push is all that is required; the workflow file is already in place.
