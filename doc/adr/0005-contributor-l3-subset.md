# ADR 0005 — What a Contributor may reach inside L3

**Status:** Accepted · 17 August 2026
**Decider:** Parul Bhoite ("use your proposed default")
**Resolves:** `D5` in `DECISIONS-REQUIRED.md` · doc 06 §11.5

## Context

Doc 06 §2.3 says a Contributor gets *"own department, restricted subset — excludes department-wide financial aggregates and other people's records."* That is a principle, not a specification, and doc 06 §11.5 lists the detail as genuinely open: *"exactly which department data a contributor sees needs defining per department with a design partner."*

It cannot stay open. Doc 07 M4's acceptance is **"a Contributor cannot reach L3 aggregates"** — an assertion that needs a definition of "aggregate" to test against. Without one, the acceptance test would assert whatever the implementation happened to do.

The correction doc 06 encodes is worth restating, because it is the reason this boundary exists at all: **Contributor is not a junior Manager.** A salesperson should be able to work their own pipeline without holding every deal value in the company. The failure mode is not a dramatic breach — it is a junior hire who can read the whole department's numbers because nobody defined what "restricted" meant.

## Decision

A Contributor, within their own department at L3, **may reach**:

1. **Records they own or are assigned to** — `owner_user_id` or `assignee_user_id` matches the caller.
2. **Records they created** — `created_by_user_id` matches the caller.
3. **Department reference data** — pipeline stages, the service catalogue, the price list, SOPs, templates. Shared context that describes how the department works, not what it is currently doing.

And **may not reach**:

4. **Any aggregate computed over the department** — sums, counts, averages, min/max, percentiles, forecasts, health scores. Regardless of which records feed it.
5. **Any record owned by another user**, even within their own department.
6. **Any field marked `sensitivity: financial`** on a record they do not own.

### Two consequences that follow, and are deliberate

**An aggregate over only your own records is still denied.** A Contributor with one deal could otherwise read the department total by inference when they are the only record. Allowing self-scoped aggregates would make the boundary depend on how many records happen to exist, which is not a boundary.

**Denial renders `Locked`, not `0`.** I10 applies here as everywhere: a Contributor sees "Requires a manager role" with the capability named, never a zero that reads as "the pipeline is empty". Doc 06 §4.5 permits disclosing that a capability exists and is gated; it forbids disclosing the value or any function of it.

## Consequences

- The rule is a pure function, `decide_l3_access`, so it is testable in isolation and has one definition rather than one per endpoint.
- Contributors get a genuinely useful surface — their own work, plus the reference data needed to do it — rather than a crippled Manager view.
- **This is a default, not a finding.** Doc 06 §11.5 asks for it to be set per department with a design partner. It is deliberately uniform across departments for now; the first design partner is expected to move it, and moving it should be an ADR rather than an edit.
- The `contributor_restricted` flag already carried on `ScopedSession` since M1 now has behaviour behind it.

## Revisit

With the first design partner, per doc 06 §11.5 — and specifically to ask whether rule 3 (reference data) is too narrow for Operations, where a site supervisor may need to see a colleague's task to do their own.
