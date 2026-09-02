# NEXUS OS — Vision and Build Plan

**Status:** the working agreement between Parul and Claude · supersedes `doc/07` as the *plan*
**Version:** 1.0 · 25 August 2026
**Companion documents:** `ARCHITECTURE-HLD.md` (what the system is) · `ARCHITECTURE-LLD.md` (how it is built) · `BUILD-STATUS.md` (where it actually stands) · `DECISIONS-REQUIRED.md` (what is still open)

> ⚠️ **§6 is superseded, 25 August 2026.** The application flow changed. The vision in
> §1, the invariants in §3 and the working agreement in §7 stand unchanged and remain
> the contract. **§6's nine phases are replaced by the twenty-two in
> `doc/12-IMPLEMENTATION-PLAN.md`**, built from the new flow in `doc/09` and the
> decisions in `doc/11`. Read §1, §3 and §7 here; take the plan from doc 12.

> **What this document supersedes.** `doc/07-Claude-Code-Build-Prompt.md` remains on
> disk and its §2 invariants stay binding, cited across the ADRs and the test suite.
> What it no longer governs is the *sequencing*: §6's fourteen milestones are replaced
> by the nine phases in §6 below, because five of the first six milestones are marked
> complete in a state the code does not support. The reading list in doc 07 §1, the
> stack in §3 and the out-of-scope list in §8 are all still in force.

---

## 1. The vision

**For businesses in Oman and the wider GCC that cannot afford a full executive
team, NEXUS OS is an AI business operating system that learns the company once,
then continuously tells the owner what changed, what it means, and what to do
about it — and executes the work.**

Every competing tool answers *"what happened?"*. NEXUS answers *"what should I
do about it?"*, and then does it.

### The loop is the product

```
   Connect ──▶ Understand ──▶ Decide ──▶ Execute ──▶ Improve
      │                                                  │
      └──────────────────  Company Brain  ◀──────────────┘
```

Anything that does not close that loop is a feature, not the product. A dashboard
that stops at *Understand* is a BI tool, and BI tools are a solved, crowded,
low-margin market.

### The moat is the Company Brain, not the feature list

Any single feature is copyable in a quarter. A customer's accumulated business
context — their documents, their price list, their pipeline, their corrections to
what we inferred — is not, and it compounds every week they use the product. This
has three consequences we design around rather than discover later:

1. **Onboarding is not a form, it is the beginning of the moat.** Every question we
   ask that a crawler could have answered is a tax on the thing that makes the
   product defensible.
2. **The permission model is a product feature, not plumbing.** A shared brain is
   only usable if a Sales contributor cannot read the payroll file somebody
   uploaded into it. This is why the scoped retrieval layer is the security core
   and not an afterthought.
3. **Corrections are the highest-value input we receive.** A user fixing an
   inferred fact is worth more than ten crawled pages, and the system must treat
   it that way (user-confirmed outranks every other source).

### Trust is an engineering problem

A card that says *"increase Google Ads budget 15%, confidence 89%"* is worse than
worthless if the 89% came out of a language model. The product's entire position
rests on the opposite claim, so the claim is enforced in code and in CI rather
than in prompts:

> **The model interprets and phrases. It never produces a number.**

Every figure a user sees is fetched from a source system or computed by
deterministic Python, and can be traced back to its inputs. This is invariant I1,
and it is the reason `calculators/` contains no model and `retrieval/` is the only
path to data.

### Regional fit, by default

OMR/AED/SAR currency, GCC business norms in tone, tender-driven procurement,
Arabic content in a later phase. HubSpot, Jasper and Semrush are built for US/EU
norms; that gap is real and defensible, and it is cheap to hold if we build for it
from the start rather than localising later.

---

## 2. What NEXUS OS is — and is not

| It is | It is not |
|---|---|
| Seven AI directors reading one shared Company Brain | Seven chatbots with seven knowledge bases |
| A layer that connects to the customer's CRM and accounting | A replacement CRM (reversed by decision, Aug 2026) |
| A system that says *"I cannot show this — connect X"* | A system that fills a gap with a plausible estimate |
| An operations layer that is the customer's system of record for delivery | A project-management tool sold on its own merits |
| Deterministic maths narrated by a model | A model asked to reason about numbers |

**The Operations layer carries unusual weight.** Because NEXUS connects to a CRM
rather than replacing it, Operations is the only first-party data NEXUS owns. Its
adoption — not CRM adoption — determines whether the executive layer ever has
anything real to reason about.

---

## 3. The ten invariants

These are the reasons the product exists. A change that violates one is a bug
regardless of what else it achieves. Carried forward from doc 07 §2 unchanged;
each names the test that proves it and the code that holds it.

| # | Invariant | Held by | Proved by |
|---|---|---|---|
| **I1** | **Never invent a number.** Every figure is fetched or computed by deterministic Python | `calculators/` is pure and contains no model | `/evals/grounding` — *not yet written* |
| **I2** | **Identity is bound to the session, never a tool argument.** Retrieval takes a query, never a `user_id` | `ScopedSession` constructed per request; tools closed over it | `test_retrieval_signatures.py` (signature-level) + `/evals/permissions` — *runtime proof not yet written* |
| **I3** | **Filter before search.** The permission predicate is part of the query, for vector *and* relational reads | Scope columns on the chunk row; RLS plus a department predicate | `test_tenant_isolation.py` (tenant half) — *department half not yet built* |
| **I4** | **Default deny on classification.** Any chunk that fails parsing or classification, or falls below threshold, becomes L5 and enters review | `documents/classify.py:_withhold` — the single failure outcome | `test_classification_default_deny.py` ✅ |
| **I5** | **Caches are keyed by the caller's resolved scope set**, not by tenant | `ScopedSession.cache_key()` | `test_scope_cache_key.py` (derivation) — *no cache exists yet to key* |
| **I6** | **Derived artifacts inherit `max(scope of inputs)`.** Declassification is an explicit logged human act | *not yet built* | — |
| **I7** | **Untrusted content is data, never instruction.** No external action from a tainted turn without human confirmation showing the payload | *not yet built* | `/evals/injection` — *not yet written* |
| **I8** | **No agent has shell access.** Calculators are MCP tools or direct calls, never skill-bundled scripts | No agent layer exists yet | — |
| **I9** | **Every number is auditable** — input snapshot, calculation trace, prompt version, cost | `generation` table — *not yet built*; `audit_log` exists in schema and **is never written** | — |
| **I10** | **Never a zero, never a blank.** A missing input renders a named state | Seven render states; `DELIVERED` is empty so every tile says so | `test_dashboard_scope.py` ✅ |

**Four of ten are currently proved. Three have no code behind them at all.** That
is the honest position, and it is the reason Phase 5 comes before Phase 8.

---

## 4. Where we actually are

`BUILD-STATUS.md` carries the full audit. The summary that drives this plan:

- **~32% complete.** The foundation is strong — forced RLS proved against Neon, a
  real SSRF guard, role→scope as data, honest optional-dependency boundaries for
  the model and the embedder.
- **The authenticated product has no working entry point.** A new customer cannot
  create a workspace through the UI, because the only endpoint that inserts one has
  no page and no proxy in front of it.
- **Document ingestion has never run against a database.** Two check-constraint
  violations sit in `main`; the one test covering the path monkeypatches the write.
- **There is no retrieval layer**, so a stored document can never be read back.
- **CI has never executed** (no remote), and when it does it will skip all 92
  database tests including the entire isolation suite.

Five entries in the retired `TASKS.md` claimed completion the code does not
support. That is what the phase gate in §7 exists to prevent recurring.

---

## 5. Product surface at MVP

Seven directors, one brain, six scoreable departments. What each director can
honestly do on day one with **no integrations connected** — from doc 04's truth
table and doc 05's widget lists, confirmed by ADR 0010:

| Director | Works with website + documents only | Needs a connection |
|---|---|---|
| **Chief of Staff** | Brain status; Health Score once one department is scoreable; department briefings. Week 1 shows a **Baseline**, not a Morning Brief | Everything else |
| **Marketing** | Growth Planner, Content Studio, brand audit, SEO market half, competitor discovery | GA4 for traffic — and Marketing is **not scoreable without it** |
| **Sales** | Lead Intelligence, Proposal Studio (needs an uploaded price list, every price cited), outreach drafting | CRM for the whole pipeline half |
| **HR / People** | Directory from the onboarding roster, policy library and generator, JD generator, onboarding checklists | Ops task assignment for utilisation |
| **Operations** | Everything, once the customer creates their first project — it is the first-party layer | Nothing |
| **Strategy** | Market position from competitor data, crawl and SEO share | Finance and Ops live, for portfolio and bid/no-bid |
| **Finance** | **Nothing.** Every doc 05 §5 widget needs the accounting API, which is out of scope | **D7 is still open** — manual entry labelled self-reported is the recommendation |

**The rule that makes this safe to ship:** a tile is either backed by a real
computation or it says what it needs. There is no third state, and no outlined
widget that a screenshot cannot distinguish from a working one.

---

## 6. The build plan

Nine phases. Each has an acceptance test, not a checklist. Work item IDs (C1, H4,
M9…) refer to `BUILD-STATUS.md` §13, which carries the file-level detail.

### Phase 0 — Settle what blocks the code · *your input, ~2 days*

Not engineering. Five answers and one repository action.

| Blocker | Why it cannot wait |
|---|---|
| **D14** — login rate limiting shape | A sign-in form is already live and unprotected |
| **D17** — where doc 08 sits in precedence | Blocks every further onboarding change |
| **D4** — production email provider | Blocks Phase 2's verification flow reaching a real inbox |
| **D13** — Anthropic access and model tier | Blocks Phase 7 entirely |
| **D7 (Finance)** + **D8** (capability count) | Blocks Phase 8 planning, not Phase 8 start |

**Plus: create a git remote.** CI has never run. That is the direct cause of two
check-constraint violations sitting in `main` and of the isolation suite proving
nothing outside this machine.

**Done when:** the five decisions are recorded as ADRs and `git push` works.

---

### Phase 1 — Make what is claimed done actually true · *~4 days*
`C1 C2 C5 C6 C7 C8 C12`

No new features. One migration reconciles the two check-constraint violations
(`review_state` vocabulary, `document.status='superseded'`). CI gets a Postgres
service, runs Alembic up **and** down, and fails the build if the database suite
silently skips. The config stops defaulting to non-secure cookies and public API
docs, and the no-op secret validator becomes a real startup refusal.

**Acceptance test:** CI is green on a remote runner, with the tenant-isolation
suite reported as *executed*, not skipped — and a deliberately broken RLS policy
turns it red.

---

### Phase 2 — Give the authenticated product an entry point · *~7 days*
`C3 C10 C4`

Domain-claim UI and the three missing BFF proxies. Email delivery wired through
`FileMailer` — the whole verification and invitation chain works locally without a
provider, so D4 gates deployment, not development. Then the one end-to-end test
that walks the real journey.

**Acceptance test:** a stranger registers, verifies their email, claims a domain by
DNS TXT, lands in a workspace, completes onboarding, invites a colleague, uploads
a document and sees it in the review queue — with no manual API calls, and the
whole path asserted in CI against Postgres.

*This is the phase after which the product exists.*

---

### Phase 3 — Close the security surface · *~7 days*
`C9 H13 H7 H10 H5`

Login and register rate limiting with argon2 moved off the event loop; the
fourteen open items in `AUDIT-FINDINGS.md`; RLS on `domain_claim`; a global
exception handler that preserves `x-request-id`; and the audit trail that `I9`
needs and that nothing currently writes.

**Acceptance test:** a credential-stuffing script gets backed off without ever
revealing whether an address exists, and every state-changing action in the
product leaves an `audit_log` row that a workspace admin can read and a
non-admin cannot.

---

### Phase 4 — Make deployment possible · *~7 days*
`C11 H8 M15`

Container images for API and web, a stack that runs all three services, migrations
as a deploy step, TLS termination, and secrets from somewhere other than a file on
one laptop. Then the frontend test harness — Vitest for components and BFF
handlers, Playwright for the Phase 2 journey — which can only exist once there is
something deployable to run it against.

**Acceptance test:** a fresh machine with Docker and one secrets file brings the
whole product up, migrated, on HTTPS, and Playwright drives the Phase 2 journey
against it.

---

### Phase 5 — M6, the security core · *~11 days*
`H2 then H1`

`/evals/permissions` is written **first**, as executable red-team specs: a
Contributor reaching L3 Finance, existence disclosure, a spoofed identity
argument, cross-workspace retrieval after a switch, cached reuse across roles.
Then the retrieval layer that has to survive them — one path for vector and
relational, identity bound at construction, the permission predicate inside the
query, `SET LOCAL hnsw.iterative_scan = relaxed_order` on every ANN call (ADR 0012
measured 5% recall without it), citations inheriting permissions, and `Locked` as
a distinct response type from filtered-out.

**Acceptance test:** every red-team case fails to leak, the suite runs in CI, and
removing the predicate from a single query turns it red.

*Everything after this depends on it. Nothing before it is safe to skip.*

---

### Phase 6 — Make documents useful · *~10 days*
`H3 H4 M4`

A real classifier behind the existing gate — the gate does not change, which is
the point of having split them. Then upload and review-queue UI, then list and
signed download.

**Acceptance test:** upload a payroll-shaped file; it is withheld, appears in the
queue with its reason and confidence, and becomes reachable to exactly the right
people the moment a reviewer approves it — and to nobody before.

---

### Phase 7 — The Company Brain, then grounding · *M7 then M8*
`H12`

The Brain assembles crawl facts, onboarding answers and document content with
provenance on every one, and the review gate lets the owner correct them. Conflict
precedence is user-confirmed > connected system > crawl > inference, and a later
crawl that contradicts a confirmed fact raises re-confirmation rather than
overwriting.

Then grounding: the Company Context assembler as the single path, the `generation`
table with input snapshot and calculation trace, and the pipeline
fetch → compute → one model call → schema-validate → retry once → **Unavailable**.

**Acceptance test:** I1 and I9 become testable for the first time — a
model-produced number is rejected by the pipeline, and every displayed figure
traces to a `generation` row that names its inputs.

---

### Phase 8 — Dashboards, one director at a time · *M9*
`M1`

The global shell first — data ribbon with freshness, period selector, completeness
meter, all seven render states, and the assistant panel reserved in the layout
because retrofitting a persistent side panel into seven finished dashboards is a
rewrite of all seven. Then Marketing end to end, then one director per increment,
adding an offering id to `DELIVERED` only when its data path is real.

**Acceptance test:** disconnect each source in turn and every affected tile
degrades to a named state that says what to connect. No tile ever shows a zero.

---

### Phase 9 — Integrations, Operations, agents, admin · *M10 → M13*

In that order, and the order is not arbitrary. M10 turns Marketing Partial → Live
and gives Sales its pipeline half. M11 creates the first-party data the Ops and HR
widgets need, and is the layer the whole executive surface ultimately rests on.
M12 fills the panel M9 reserved, with `/evals/injection` written before the agents
that must survive it. M13 closes the loop: artifacts with scope inheritance, the
workspace and internal admin consoles, and the full eval harness gating CI.

**Acceptance test:** CI fails on a grounding, permission or injection regression —
deliberately break one and watch the build go red.

---

## 7. How we work

Carried forward from doc 07 §5, with one rule added and one removed.

1. **One phase at a time.** At the end of each I stop, report, and wait for you to
   validate using the acceptance test above.
2. **Write the invariant test before the feature it guards**, for anything touching
   permissions or grounding. This is why Phase 5 writes `/evals/permissions` before
   the retrieval layer, and why Phase 2's journey test precedes Phase 6's classifier.
3. **No mock data in the running app.** If data is unavailable, render the honest
   state. A widget outline and a working widget are indistinguishable in a
   screenshot, and the screenshot travels.
4. **No `TODO` or placeholder in completed work.** Currently true — the codebase has
   zero of either, and it is worth keeping.
5. **Small commits.** No unrelated refactors inside a feature commit.
6. **If the spec is ambiguous or two documents disagree, stop and ask.** Record every
   decision you make in `doc/adr/NNNN-title.md`. No resolution is invented.
7. **NEW — a phase is complete when its acceptance test has run green in CI against
   a real Postgres, driven through the application rather than around it.** Not when
   the code exists, not when a unit test passes over a monkeypatched write. This
   rule exists because five milestone entries claimed completion for paths that had
   never executed.
8. **REMOVED — the `MILESTONE-N.md` note.** Six of them agreed with each other and
   disagreed with the database. `BUILD-STATUS.md` is regenerated at the end of each
   phase instead; the evidence is the CI run.

### Document precedence

Where documents conflict, in order: **this document** (for plan and sequencing) >
`doc/07` §2 and §8 (invariants, out-of-scope) > `doc/06` > `doc/05` > `doc/04` >
`doc/03`/`doc/01`. Conflicts settled by that rule are listed in
`ARCHITECTURE-HLD.md` §2. Anything not settled by it goes to
`DECISIONS-REQUIRED.md` — never invent a resolution. `doc/08`'s place in this order
is **D17**, still open.

---

## 8. Out of scope

Unchanged from doc 07 §8: Business Simulator · Decision Intelligence · Voice ·
Board Packs · Meta publishing · a second CRM connector · accounting integration ·
Arabic localisation · billing beyond a trial flag · anything marked Phase 2 or 3
in doc 05.

Two consequences worth restating, because both shape a phase:

1. **Accounting being out of scope is why the Finance Director has no inputs.** D7
   is the choice between shipping it as structure plus named unlocks, bringing
   accounting in, or allowing manual entry visibly labelled self-reported. Doc 04
   §7 already sanctions the third.
2. **If something out of scope turns out to be required for something in scope,
   stop and say so** rather than building it.

---

## 9. Risks we are carrying deliberately

| Risk | Why we accept it now | What would change the answer |
|---|---|---|
| **Scope.** The prototype is a materially bigger product than the written scope | An explicit MVP cut exists and the phases enforce it | Any phase growing past its acceptance test |
| **Cold start.** None of the headline numbers exist on day one | Six of seven directors have real content with nothing connected; honest states cover the rest | A design partner finding the empty state unusable |
| **Filtered-ANN recall.** Measured at 5% without iterative scan | ADR 0012 settled it: one index plus `iterative_scan` | Cardinality far above the spike's assumptions |
| **The embedding pass runs in the API process** | Acceptable only while the ~2 GB model is absent by default | Installing `[embeddings]` in production — `M15` moves it first |
| **In-process scheduler on every API process** | The sweep is idempotent and the threshold is documented | More than one API process in production |
| **Single-vendor model dependency** | ADR 0011 makes no key a supported state, so absence is not an outage | — |

---

## 10. What I need from you to start Phase 1

1. **D14, D17, D4, D13** answered — and **D7/D8** before Phase 8 is planned.
2. **A git remote**, so CI runs at all.
3. **Your agreement to this plan**, specifically: that Phase 1 spends four days
   making existing claims true before any new feature is built, and that the
   phase gate in §7.7 replaces the milestone note.

Everything else can wait for the phase that needs it.
