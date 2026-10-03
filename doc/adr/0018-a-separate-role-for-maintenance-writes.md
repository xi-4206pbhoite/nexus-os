# ADR 0018 — Maintenance writes get their own database role, not a bypass

**Status** Accepted
**Date** 3 September 2026
**Decided by** Parul, answering **D24**. Option B of three.

## Context

`doc/12` §Phase 4 requires row-level security on `domain_claim`, with a
`user_id`-scoped predicate — the workspace predicate every other table uses has
nothing to key on, because a claim exists *before* a workspace does.

Written literally, that breaks two paths, and **both fail silently**, which is
the failure shape this repository has already met three times (a drifted schema,
a proxy filtering GUCs, an unpinned resolver — all green somewhere that was not
production).

**The expiry sweep would update nobody's rows.** `jobs/expiry.py:
expire_stale_claims` runs one statement across every user's claims on an
unscoped session. Under `FORCE ROW LEVEL SECURITY` with no `nexus.user_id` set,
it matches zero rows and reports success. Abandoned claims would accumulate for
ever while the job logged a clean run — the same shape as the
`next_run_time=None` bug in `scheduler.py`: a job that runs, does nothing, and
says nothing.

**The dispute write is to somebody else's row.** When a second claimant loses a
race, `create_workspace_for_claim` marks *their* claim `disputed`. The actor is
the winner; the row belongs to the loser. A `user_id` predicate refuses it, so
`DomainDisputedError` is raised over a row that was never marked — leaving the
support conversation the record exists for with no artefact at all.

Three options were costed. **B was chosen.**

## Decision

**A second login role, `nexus_jobs`, owns the writes that are legitimately not
one user's.** `nexus_app` keeps the `user_id` predicate and can never see or
touch another person's claim.

**Not a GUC-keyed bypass** (option A). That was the cheap answer: a second
permissive policy keyed on something like `nexus.maintenance`, set only by the
sweep. It fails on the principle ADR 0008 already establishes for
`neondb_owner` — **the isolation guarantee is only worth what the connecting
role cannot do.** A GUC is application state. Anything that can set one gets
full read of every claim in the system, so the boundary moves out of the
database and into application code, which is exactly where it stops being
structural. The whole argument for RLS here is that no application bug can
defeat it.

**Not a policy encoding business rules** (option C). Scoping by
`user_id OR disputes_workspace_id` makes the policy restate a rule the
application also states, and the two will drift. It also turns one sweep
statement into one per user.

### `nexus_jobs` is not privileged

It is `NOSUPERUSER NOBYPASSRLS`, exactly like `nexus_app`, and
`db/bootstrap.sql` verifies both flags rather than trusting the `ALTER` — Neon
rejects `ALTER ROLE … NOSUPERUSER` outright, so the existing rule applies
unchanged: **tolerate the statement, prove the outcome.**

What it has instead is a **role-targeted policy**:

```sql
CREATE POLICY domain_claim_maintenance ON domain_claim
    TO nexus_jobs USING (true) WITH CHECK (true);
```

`TO role` is the mechanism that makes this a boundary rather than a hole. The
permission is attached to an identity that must authenticate with its own
credentials, on tables named one at a time — not to a runtime flag any code path
can set.

### What it may touch

`domain_claim` only, for now. Every future maintenance policy is a deliberate
addition, and the burden is on the person adding it to say why the app role
cannot do the work.

## Consequences

- **Every environment must provision a second credential.** That is the cost the
  option was chosen with open eyes: `db/bootstrap.sql`, `.env.example`, the CI
  workflow and any deployment each grow one. A missing `NEXUS_JOBS_DATABASE_URL`
  must be a **startup refusal**, not a fallback to `nexus_app` — falling back
  would restore exactly the silent-zero-rows failure this ADR exists to prevent,
  and it would do so in production while every test passed.
- **The dispute write happens on a different connection**, so it is a separate
  transaction from the workspace creation that triggers it. That is correct
  rather than incidental: the workspace creation aborts with
  `DomainDisputedError`, and the dispute record must **survive** that abort. It
  is the artefact the support conversation needs.
- **`create_workspace_for_claim` now touches two roles.** Worth watching: it is
  the only request-path function that does, and the reason is that recording a
  conflict is a system act rather than a user's. If a second such case appears,
  the pattern deserves a name rather than a repeat.
- **The sweep can no longer be run by the app role at all**, which is the point
  — the failure it had was invisible precisely because the app role was allowed
  to try and simply matched nothing.
