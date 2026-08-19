# ADR 0013 — A workspace exists without a verified domain

- **Status:** Accepted
- **Date:** 18 August 2026
- **Decider:** Parul Bhoite ("skip workspace requires a verified domain — remove")
- **Supersedes:** doc 07 M3's invariant, *"no workspace exists without a verified domain"*

## Context

Doc 07 M3's done-when was *"no workspace exists without a verified domain, and
Preview data expires"*, and `create_workspace_for_claim` was written as the only
path that inserts a workspace, with every precondition checked in that one place.

The consequence, reproduced against the live API:

```
register -> 201, signed in
/auth/me -> 403 No workspace selected
```

A new account could sign in and reach nothing. Every workspace-scoped screen —
onboarding, dashboards, documents — answered 403, because a workspace required a
verified domain and verifying one requires controlling its DNS. The product's own
account page said as much: *"Signing in works. Everything a workspace would contain
does not."*

That is a defensible position for a build sequenced M0→M13. It is not compatible
with a registration flow that collects company details, department questions and a
persona, which is the next feature.

## Decision

**Registration creates a workspace immediately, with no verification.**
`create_workspace_at_registration` is a second creation path;
`create_workspace_for_claim` is unchanged and remains the only path to a *verified*
domain.

The domain is **inferred** from the sign-up email, since the form asks for a work
address, and stored with `domain_verified_at IS NULL`. A free email provider yields
**no** domain rather than a wrong one — a workspace claiming `gmail.com` would be a
workspace for Gmail, and `domain` is what the crawler and the Company Brain will
treat as the company, so a wrong value there would seed the Brain with facts about
a mail provider.

**No migration was required, and that is evidence rather than convenience.**
`workspace.domain` and `domain_verified_at` are both nullable, and the unique index
is partial:

```sql
CREATE UNIQUE INDEX ix_workspace_domain_verified
    ON workspace (lower(domain)) WHERE (domain_verified_at IS NOT NULL);
```

`test_the_uniqueness_only_applies_to_verified_domains` has asserted that since
migration 0002. The schema always permitted an unverified workspace; only the
application refused to make one.

## What verification is for now

It stopped being a gate and became a claim to **exclusivity**. First verified wins
(doc 06 §1.1), decided by the partial unique index rather than application timing,
and the loser still gets a dispute record. None of that changed.

## What this gives up

**Two workspaces can hold the same domain string, as long as at most one is
verified.** A stranger registering `someone@acme.om` gets a workspace naming
`acme.om` that nobody checked. Three things bound the damage and none removes it:

- **Row-level security is per workspace, never per domain.** The two see nothing of
  each other; the domain string is a label here, not an authorisation input.
- **`owner_claim_review` is set** on every workspace created this way, because an
  inferred domain is precisely an unreviewed owner claim. Nothing gates on the flag
  yet — it is the artefact a support conversation will need, recorded as that and
  not as a control.
- **Verification stays available**, so the real owner can always take the exclusive
  slot. `test_an_unverified_workspace_does_not_block_a_later_verified_one` proves a
  squatter cannot make that impossible, which would have made this terminal.

Both consequences are asserted in `test_workspace_at_registration.py` rather than
left as prose here, so that if someone later adds a unique constraint across all
domains, registration breaking is a test failure rather than a support ticket.

## Consequences

- Doc 07 M3's done-when is no longer true as written. `TASKS.md` M3 keeps its
  history; this ADR is what supersedes the claim.
- `test_workspace_gate.py` needed no test rewritten — every case there was always
  about claim mechanics and the partial index. Only its framing docstring changed,
  from "no workspace exists without a verified domain" to what the database
  actually enforces.
- The sign-up page's copy — *"You will claim your company's domain next, and that is
  what creates the workspace"* — became false and is rewritten.
- A workspace is created **before** the session is issued, so `_sign_in` finds
  exactly one membership and auto-selects it. A workspace that exists but is not
  selected is still a dead end, since the active workspace is resolved server-side
  from `user_session`.
- Creation is guarded on the caller holding **no** membership, not on having just
  registered: registration doubles as the idempotent re-submit path (ADR 0014), and
  an existing member must not collect a workspace per submission.

## Latency, measured rather than assumed

Adding workspace creation made registration the heaviest request in the product and
pushed it past the web proxy's 15s timeout, which aborted a request the API had
already completed — the account existed, the browser saw a 503. Only ADR 0014's
idempotent re-registration made a retry recover.

Instrumented against Neon in `us-east-2` from a development laptop:

```
open session        0.03s   (SQLAlchemy connects lazily)
register_user       5.94s   <- first statement, pays connection setup
authenticate        0.60s
memberships         1.06s
create_workspace    1.32s
memberships         0.53s
issue_session       0.79s
commit              0.28s
                   10.56s
```

Warm round trip is ~0.26s; a *new* connection costs ~1.5s and a cold Neon compute
~9.7s. So the cost is per-round-trip and per-connection, not per-row, and argon2 —
the usual suspect, and a known open finding — is 33ms of it.

Two things were done and one deliberately was not:

- **Three inserts became one statement.** Tenant, workspace and membership are now a
  single CTE, because the ordering the CTEs express is the ordering the foreign keys
  already required. The membership read is passed into `_sign_in` rather than
  repeated. Together ~1s.
- **The proxy timeout went to 30s**, with the numbers above recorded beside it. A
  timeout that fires while the server succeeds is a lie to the client.
- **Nothing was made asynchronous or cached.** Deployed, the API sits beside its
  database and this request is tens of milliseconds; the 10s is the development
  setup reaching across an ocean, and optimising the application for that would be
  optimising for the wrong deployment.

## Revisit when

Two strangers from one company actually collide in practice, which is when
`owner_claim_review` needs to become a control rather than a flag — most likely as
part of the invitation flow, so the second person is offered *join* rather than a
second workspace. Also when domain verification is surfaced in the product as a
trust badge, which is the form it now takes.
