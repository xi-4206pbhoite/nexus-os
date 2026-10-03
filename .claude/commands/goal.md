---
description: Execute the NEXUS OS implementation plan phase by phase, tests first, acceptance-gated
argument-hint: [phase number, or blank to continue from the first incomplete phase]
---

# GOAL — Build NEXUS OS to the implementation plan

You are the engineer taking this codebase from ~32% to complete. Work through
`doc/12-IMPLEMENTATION-PLAN.md` **in order**, one phase at a time, and do not stop
between phases unless a stop condition below is met.

## 1. Read before you write

Read these in full, in this order. They override anything you infer from the code:

1. `CLAUDE.md` — shell rules, database facts, invariants, conventions
2. `doc/12-IMPLEMENTATION-PLAN.md` — the plan. §"Standing rules" applies to every phase
3. `doc/11-FLOW-DECISIONS.md` — every decision already made. **Authoritative.** Do not
   re-decide anything settled here
4. `doc/09-NEW-APPLICATION-FLOW.md` — the nine-stage journey you are building
5. `BUILD-STATUS.md` — where the code actually stands
6. `ARCHITECTURE-LLD.md` — module map, schema, RLS policies, endpoint contracts

Then read `doc/06-User-Journey-and-System-Design.md` and
`doc/05-Department-Dashboard-Offerings-and-Data-Assumptions.md` when a phase touches
the journey or a dashboard, and `doc/08-...` when a phase touches onboarding questions.

## 2. Which phase

If `$ARGUMENTS` names a phase, start there. Otherwise determine the first incomplete
phase from `BUILD-STATUS.md` and `git log`, state which one you picked and why, then
begin.

## 3. The loop, per phase

For each phase, in this exact order:

1. **Restate the phase** — its goal, its Build list, its Do-not-build list, and its
   acceptance test. If anything is ambiguous, resolve it against `doc/11` first and
   ask only if `doc/11` is silent.
2. **Write the tests named under "Tests first"** — and run them. **They must fail**,
   for the right reason. A test that passes before the feature exists is testing
   nothing; fix it before continuing.
3. **Build** the Build list. Nothing from the Do-not-build list, and nothing not on
   either list without saying so.
4. **Run the full gate:** `.\scripts\ci.ps1`. It must be green.
5. **Run the acceptance test** against a real Postgres, driven through the
   application. Not a unit test over a patched write.
6. **Prove the test can fail** — break the thing the acceptance test guards, watch it
   go red, restore it. Report both results. This step is not optional; it is the
   difference between a test and a decoration.
7. **Regenerate `BUILD-STATUS.md`** — rewrite it, do not append. Update the phase's
   status and the pending work list.
8. **Write an ADR** at `doc/adr/NNNN-title.md` for any decision you took along the way.
9. **Commit** with a message naming the phase. Small commits within the phase are
   better than one large one.
10. **Report** in three lines: what the acceptance test proved, what you deliberately
    did not build, and anything you found that the plan did not anticipate. Then start
    the next phase.

## 4. Stop conditions — stop and ask, do not work around

- The acceptance test cannot be made to pass, and you have tried twice.
- A decision is needed that `doc/11` does not answer and `doc/12` does not assume.
- Making a test pass would require **widening a permission predicate**, weakening an
  invariant, or connecting as a superuser or `BYPASSRLS` role. Never do any of these.
  Stop and explain.
- You need a credential, an external account, or an action outside this repository —
  including **creating the git remote in Phase 0**, which only Parul can do.
- Your context is running low. Commit, regenerate `BUILD-STATUS.md`, report the phase
  you are mid-way through, and stop so `/goal` can be re-invoked cleanly.
- A phase turns out to be materially larger than its estimate. Say so rather than
  silently sprawling.

## 5. Skip anything needing an external tool or credential

**Do not attempt any test that requires connecting a real external service or
account.** No credentials exist for these yet.

| Skip | Where | Do this instead |
|---|---|---|
| Live GA4 / Search Console / PageSpeed connection | Phase 18 | Build the connector and its normalisation. Test against **recorded fixtures** committed to the repo. Skip the live acceptance test |
| Live CRM connection (Zoho) | Phase 18, Phase 19 Sales pipeline half | Same: fixtures, contract tests, no live call |
| DataForSEO keyword data | Phase 11, Phase 16 SEO half | Already decided: the source records `unavailable: no_credentials`. **Never estimate a volume.** Assert the unavailable state |
| Real SMTP delivery | Phase 3, Phase 17 | Use `FileMailer` — assert the `.eml` file under `.mail/`. Build `SmtpMailer` and unit-test it against a local stub; do not send |
| Anthropic API calls | Phase 14, Phase 20 | Use `ScriptedProvider` and `UnavailableProvider`. Per ADR 0011 no key is a **supported state** — assert the unavailable path works |

**Mark a phase whose only outstanding item is a live-credential test as
`code complete — live verification deferred`, not as complete.** Record exactly which
acceptance criterion was not exercised, in `BUILD-STATUS.md` and in the phase report.
Do not quietly claim it passed.

Everything else in every phase is in scope, including all database, permission,
grounding and injection tests — those need no external service.

## 6. The registration email

For **manual walkthroughs and any seeded development account**, register as:

```
parulbhoite315@gmail.com
```

Use it in `scripts/smoke.ps1`, in any seed or bootstrap script, and when you walk a
flow by hand to check it.

**Never use it in an automated test.** Automated tests generate a fresh address per
run (`nexus-test+<uuid>@example.invalid`) so that:
- the suite stays hermetic and repeatable,
- CI does not depend on a real inbox,
- and re-running a test does not collide with an existing `app_user` row.

Until real SMTP credentials are configured, verification and invitation mail is
written as `.eml` files under `.mail/` by `FileMailer`. Read the token out of the file
rather than an inbox.

## 7. Rules that override convenience

Repeated here because they are the ones most easily lost in a long session.

1. **A phase is complete when its acceptance test runs green in CI against real
   Postgres, driven through the application.** Not when the code exists.
2. **Write the invariant test before the feature it guards** — permissions and
   grounding especially.
3. **No mock data in the running app.** A missing input renders a named state, never a
   zero, never a blank, never an estimate.
4. **No `TODO`, no `FIXME`, no placeholder, no commented-out code** in finished work.
   The repo has zero of each today.
5. **PowerShell 5.1.** No `&&`, `||`, ternary or `??` in anything Parul will run.
   Prefer adding a script over handing over a command.
6. **Never connect to Postgres as a superuser or `BYPASSRLS` role.** Every isolation
   test would pass while proving nothing.
7. **Nothing outside `app/ai/` names the model vendor; nothing outside
   `app/embeddings/` names the embedding library.** Tests enforce both.
8. **No provider fabricates output.** No demo mode, no hash-derived embedding — a fake
   embedding *ranks*, and produces confident citations with no visible symptom.
9. **Stop the web dev server before `ci.ps1`.** Both write `apps\web\.next`.
10. **If the spec is ambiguous or two documents disagree, stop and ask.** Never invent
    a resolution.

## 8. Start

State the phase you are starting, confirm you have read the six documents in §1, and
begin at step 1 of §3.
