# ADR 0004 — pgvector is required from M5, not M0

**Status:** Accepted · 16 August 2026
**Decider:** Claude, correcting an over-eager gate in its own M0 work; flagged to Parul Bhoite for objection
**Amends:** migration `0001_extensions`, `/health/ready`

## Context

Migration 0001 originally raised an exception if pgvector was not installed, with the reasoning that a database lacking it would otherwise fail late, in M5, after a great deal of work had assumed it.

The requirement is real. Doc 07 §3 specifies pgvector deliberately, because it makes the permission predicate an ordinary SQL `WHERE` clause evaluated as part of the ANN query — which is how **I3 (filter before search)** is satisfied. An external vector store forcing post-filtering would leak through ranking, result counts and latency (doc 06 §4.4).

But the *placement* was wrong. Nothing in M0–M4 performs vector search:

| Milestone | Needs pgvector? |
|---|---|
| M0 Foundation | No |
| M1 Tenancy, auth, roles | No |
| M2 Crawl, Preview audit | No |
| M3 Domain verification | No |
| M4 Onboarding, persona, scopes | No |
| **M5 Documents, classification, indexing** | **Yes — embedding into pgvector** |
| M6 Scoped retrieval | Yes |

Gating four milestones on a dependency none of them uses is a self-inflicted blocker. It became a live one: this machine has no Docker, no WSL and no MSVC toolchain, so no pgvector-capable Postgres was reachable without either a hosted account or an unvetted third-party binary — and M0 could not close over a requirement it did not have.

## Decision

The requirement moves rather than softens:

| Where | Behaviour |
|---|---|
| Migration 0001 | `pgcrypto` is required. `vector` is created **if available**; if not, a `NOTICE` is raised and the migration succeeds |
| `/health/ready` | pgvector is reported as its **own dependency**, always, with `required_now: false` |
| M5 migration | Hard-requires the extension. This is where indexing begins, so this is where absence is fatal |

`DependencyCheck.required_now` was added for exactly this: a dependency a later milestone needs is still *reported*, but is not permitted to hold the service `not_ready` for work that does not use it.

## Why report it at all, if it is not required yet

Because the failure this guards against is not "pgvector is missing" — it is **"pgvector is missing and nobody noticed until M5."** Deleting the check would restore that risk. Reporting it as a named, visible state at every readiness call keeps it in view for five milestones without blocking any of them.

This is the same reasoning as **I10** applied to our own operations surface: a missing input renders a named state, never a silent success and never a hard stop that hides the detail.

## Consequences

- M0 can close against a plain PostgreSQL install, and M1–M4 can proceed on one.
- **pgvector must be resolved before M5 begins.** Three options, to be decided then:
  1. Docker Desktop + the official `pgvector/pgvector` image — cleanest, matches doc 07 §3 exactly
  2. A free hosted Postgres with pgvector (Neon / Supabase) — doc 03 §9 already recommends Supabase
  3. Local build from the official pgvector source with MSVC Build Tools — no account, no third-party binary
- **Community prebuilt pgvector DLLs for Windows exist and were deliberately not used.** Loading an unsigned third-party binary into the database server process is a supply-chain risk that should be an explicit human decision, not something adopted for convenience mid-milestone.
- A test asserts pgvector is reported and advisory, so a later change cannot quietly drop it.

## Revisit

**Before M5 starts.** This ADR should be superseded by one recording which of the three options was chosen.
