# Milestone 4 — Onboarding, persona, scope enforcement

**Status:** ✅ complete — **ready for validation**
**Date:** 17 August 2026 · 403 tests · CI green

Doc 07 M4: *"Done when the role → scope table is enforced at the API layer and a Contributor cannot reach L3 aggregates."*

`D5` is resolved and recorded as [ADR 0005](doc/adr/0005-contributor-l3-subset.md).

---

## Acceptance

**Met, in two halves.** The rule (`test_contributor_scope.py`, 27 cases) and the boundary (`test_api_scope_enforcement.py`, 13 cases).

```
=== api: ruff check ===   PASS      === web: tsc ===    PASS
=== api: ruff format ===  PASS      === web: lint ===   PASS
=== api: mypy strict ===  PASS      === web: build ===  PASS
=== api: pytest ===       PASS  (403 tests)
CI GREEN
```

---

## D5, as decided

A Contributor within their own department **may reach** records they own, are assigned to, or created, plus department reference data (stages, services, price list, SOPs). They **may not reach** any aggregate over the department, any record owned by someone else, or `sensitivity: financial` fields on records that aren't theirs.

Two consequences are deliberate and both have tests:

**An aggregate over only your own records is still denied.** A Contributor who is currently the only owner could otherwise read the department total by inference. A rule that holds only while the data is large enough is not a rule.

**Reference data is shared even when it's financial.** The price list is both, and withholding it would make Proposal Studio unusable — Contributors get a genuinely workable surface, not a crippled Manager view.

The failure this guards against isn't dramatic: it's a junior hire who can read the whole department's numbers because nobody defined what "restricted" meant.

---

## The rule is one pure function

`decide_l3_access` implements ADR 0005 and lives in `domain/access.py` — one definition, not one per endpoint. The acceptance test has a single place to attack.

**Three outcomes, not two.** The distinction is doc 06 §4.5 in code:

| Decision | HTTP | What the caller learns |
|---|---|---|
| `ALLOW` | the data | — |
| `LOCKED` | **200** + a Locked payload | the capability exists and their role doesn't reach it |
| `DENY` | **404** | nothing |

`LOCKED` is a **success**, not a 403 — it's a *rendered state*. A 403 would push the UI into an error path and tempt it to show `0`, which is exactly what I10 forbids. `DENY` is 404 rather than 403 for the opposite reason: 403 means "this exists and you may not have it", which is an existence disclosure.

Two supporting details, each tested: the `Locked` payload carries **no numeric field** (a count would be a function of the value), and `filter_records` returns a filtered list with **no count of what was removed** — "3 records hidden" is precisely the disclosure doc 06 §4.5 forbids.

Enforcement is in `deps_scope.py`, at the API layer. `guard_aggregate` *returns* `Locked` rather than raising, because a dashboard assembles many tiles and one gated tile must not fail the whole response.

---

## Onboarding answers are scope-tagged at capture

Doc 06 §2.5: *"They are not 'company facts' visible to everyone merely because they arrived through a form."*

The question catalogue is **data**, like `ROLE_GRANTS`. Every question carries its scope and — where L3 — its department. The two doc 06 names explicitly are asserted by name:

- `average_deal_size` → **L3 Sales**
- `monthly_marketing_budget` → **L3 Finance**

A test also pins what may be L1: only `company_url` and the brand-voice terms, because L1 means published or outward-facing. And `scope_for_answer` **raises on an unknown key** rather than defaulting — an answer whose scope we can't name must not be stored at a guessed one, which is I4's default-deny applied to capture.

The database backs this up: an `L3` answer with no department violates a CHECK constraint, because an L3 fact that can't be filtered by department is reachable by anyone holding any L3 access.

**Sequencing is tested too.** Pass 1 asks only what the audit needs; no money question appears there (doc 04 §2e — asking for financial figures before showing anything is what makes people abandon a form); and `brief_recipients` sits in a third stage *after* team invitation, because doc 06 §4.10 requires recipients to be workspace users and you can't pick from a list that doesn't exist yet.

---

## Persona never authorises

Doc 06 §2.6: *"Conflating presentation preference with authorisation is how access-control bugs get written."*

Asserted three ways: `ScopedSession` carries no persona field, the access rule's source doesn't mention one, and two callers differing only in presentation decide identically. If a persona field ever appears on `ScopedSession` it's one refactor from being read by a predicate — so the separation is asserted on the type itself.

## Roles are never self-declared

The `invitation` table carries the role and `invited_by_user_id`. Acceptance **copies** the role; it never supplies it. An unrecognised role is refused by a CHECK constraint, because a role with no row in the scope table would fall through every check.

---

## What does not exist

- **No onboarding UI.** The catalogue, scoping, storage and sequencing are built and tested; the wizard screens are not. This is a deliberate split — the security-relevant half is done and the screens are ordinary form work.
- **No routes for answers or invitations yet.** The tables, constraints and rules exist; `POST /onboarding/answers` and `POST /invitations` are not written. `deps_scope` is the enforcement layer they will use.
- **`decide_l3_access` is not yet wired into a query.** It is enforced at the API layer as M4 requires, but M6 is where it becomes part of the SQL predicate rather than a check applied to results. Filtering after the fact is correct for a list already scoped by RLS; it is **not** sufficient for aggregates computed in the database, which is why M6 exists.
- **Registration still doesn't send the verification email** (carried from M3).
- **The Contributor rule is uniform across departments.** ADR 0005 records that doc 06 §11.5 asks for it to be set per department with a design partner — Operations especially, where a site supervisor may need a colleague's task to do their own.

---

## How to validate

```powershell
.\scripts\verify.ps1
```

The two suites that carry the acceptance:

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest tests\test_contributor_scope.py tests\test_api_scope_enforcement.py -v
```

**The most useful thing you can do is disagree with ADR 0005.** It is a default I proposed and you ratified, not a finding — if a Contributor in Operations needs to see a colleague's task, that changes rule 5, and it should change as an ADR rather than an edit.

---

## Invariants

| | Status |
|---|---|
| **I3** filter before search | Enforced at the API layer; becomes part of the query predicate in M6 |
| **I10** never a zero | `LOCKED` is a rendered state carrying no numeric field |
| Doc 06 §4.5 | `LOCKED` names the capability; `DENY` returns nothing, with no count of what was filtered |

---

## Next

**M5 — documents, classification, indexing.** ⛔ **pgvector must be resolved before it starts** (ADR 0004). Three options: Docker Desktop with the official `pgvector/pgvector` image, a hosted Postgres with pgvector, or a local build from official source with MSVC. M5's first migration hard-requires the extension, and `/health/ready` has been reporting its absence since M0 so this is not a surprise.
