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

## Task 4.10 — the wizard and the routes

Added after the milestone's first pass, together with two defects it uncovered (see `AUDIT-FINDINGS.md`): no workspace could be created through the API, and no member could see the workspace they belonged to. Both were row-level security refusing writes and reads the application had never actually attempted against Postgres, and until they were fixed nothing built here was reachable.

**`app/routes/setup.py`** — `GET /onboarding/questions`, `POST /onboarding/answers`, `POST|GET /invitations`, `POST /invitations/{id}/revoke`, `POST /invitations/accept`.

Three properties are worth reading the code for:

- **`AnswerIn` has a `key` and a `value` and no third field.** There is no scope to spoof, because the classification is looked up in `scope_for_answer` on the write path. A request cannot store its average deal size as L1 by asking nicely, and a test asserts the module never reads a scope from the payload.
- **`AcceptIn` has a `token` and nothing else.** Doc 06 §2.2 calls a self-declared role privilege escalation via dropdown; there is no dropdown because there is nowhere to put its value. `invitations.accept()` takes no role parameter either.
- **Answering is not authorising.** The `role` and `department` questions write rows in `onboarding_answer`. Nothing in the module touches `membership`, which is the only table `build_scope` reads.

**Two migrations, both narrow SELECT policies with the same argument as migration 0003 — they disclose nothing the caller does not already hold:**

- **0008** — a user may see the workspaces they hold a live membership in. Without it, login could not resolve its own memberships.
- **0009** — an invitation row is visible to a connection that presents its token hash. Acceptance has to read the row to learn the workspace, and cannot know the workspace before reading the row.

**The wizard** (`apps/web/app/onboarding`) follows doc 04 §5's order and renders from the catalogue rather than from hand-written forms, so a question added to `app/domain/onboarding.py` appears without a frontend edit. Every question carries its scope on screen — *Sales only — managers and above* beside the deal size — which is doc 06 §2.5's *"tag them at capture"* made visible to the person it protects.

Verified end to end against Neon, as an Owner and then as a Contributor who joined by invitation. As the Contributor: `can_administer: false`, an empty member roster, both L3 money answers absent while every L1/L2 answer is present, `403` on both writes, `403` on inviting an Owner, and `404` — not `403` — on listing invitations.

---

## What does not exist

- **No audit inside the workspace.** Doc 04 §5's stage 1 — the thing that earns the right to ask everything after it — is M7. The wizard says so where the audit belongs and links to the Preview audit, which is the same engine and needs no account. There is deliberately no placeholder score: a made-up number is the one failure the product's central claim exists to prevent, and it would be on the screen either way.
- **No connections step.** Doc 04 §5 stage 4 is M10.
- **Invitations are not emailed.** Delivery is not wired up anywhere in the product (carried from M3), so `POST /invitations` returns the accept link and the inviter sends it. That is stated on the screen rather than implied.
- **Acceptance checks the address, not that it was verified.** It refuses unless the caller is signed in as the invited address; it cannot require `email_verified_at`, because nothing sends a verification email yet and every invitation would be unusable. `app/auth/invitations.py` marks where the check belongs when delivery lands.
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
