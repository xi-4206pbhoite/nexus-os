# NEXUS OS — Build Prompt for Claude Code

---

You are building **NEXUS OS**, an AI business operating system. A landing page already exists. You are building everything behind it.

Work through this in **numbered milestones**. Do not skip ahead. At the end of every milestone you **stop**, report what you built, and wait for my approval before starting the next one. I will validate each milestone myself using the validation steps given.

---

## 1. Read the specification first

Before writing any code, read these in order. They are the source of truth and they override anything you infer:

- `doc/01-NEXUS-OS-PRD.md` — product scope, MVP cut, module acceptance criteria
- `doc/04-NEXUS-OS-Flow-and-Cold-Start-Analysis.md` — what data exists at each stage; the truth table
- `doc/05-Department-Dashboard-Offerings-and-Data-Assumptions.md` — every dashboard widget and the data it requires
- `doc/06-User-Journey-and-System-Design.md` — **the primary build spec.** Journey, permission model, injection boundary, agent architecture
- `doc/03-NEXUS-OS-Architecture-and-Roadmap.md` — component design and integrations. Note: doc 06 §12 lists where this document is outdated. Where they conflict, doc 06 wins

After reading, write `ARCHITECTURE.md` summarising the system as you understand it and `TASKS.md` with the milestone breakdown below expanded into concrete tasks. Show me both before writing production code.

**If the spec is ambiguous or two documents disagree, stop and ask.** Do not invent a resolution and proceed. Record every decision I make in `doc/adr/NNNN-title.md`.

---

## 2. Non-negotiable invariants

These are the reasons this product exists. A change that violates one of these is a bug regardless of what else it achieves. Every milestone's tests must continue to prove them.

**I1 — Never invent a number.** Every figure displayed to a user is either fetched from a source system or computed by deterministic Python. The model interprets and phrases; it never produces a number. Confidence percentages, financial exposure, health scores and simulation outputs are all code.

**I2 — Identity is bound to the session, never passed as a tool argument.** Retrieval and data tools take a query, never a `user_id`. The caller's identity and resolved scope set are bound to the tool/MCP server instance at construction, outside the model's reach. A model whose context contains a crawled competitor page must not be able to request another user's scope.

**I3 — Filter before search.** The permission predicate is part of the query, never a post-processing pass. This applies to vector retrieval *and* to every relational read. Row-level security gives tenant isolation; it does not give department isolation — you must add that.

**I4 — Default deny on classification.** Any chunk that fails parsing, fails classification, or classifies below the confidence threshold becomes L5 (uploader-only) and enters a review queue. Never default to visible.

**I5 — Caches and precomputed artifacts are keyed by the caller's resolved scope set**, not by tenant alone. This includes generations, health scores, `score_history` and scheduled briefs.

**I6 — Derived artifacts inherit `max(scope of inputs)`.** Declassification is an explicit, logged, human act — never a side effect of sharing.

**I7 — Untrusted content is data, never instruction.** Crawled pages, uploaded documents, connector payloads and screen context are wrapped and labelled at every point they enter a model context. No externally-visible action (email, WhatsApp, CRM write, publish, external share) executes from a turn containing untrusted content without explicit human confirmation showing the exact payload.

**I8 — No agent has shell access.** Deterministic calculators are MCP tools or direct backend calls. Never skill-bundled scripts executed via Bash — that would void every tool allowlist.

**I9 — Every number is auditable.** Each generation persists its input snapshot, calculation trace, prompt version and cost. Any card must be able to answer "why are you telling me this?"

**I10 — Never a zero, never a blank.** A missing input renders a named state (§ data states in doc 05 §0 as corrected by doc 06 §7.1), never `0`, never an empty tile, never an estimate.

---

## 3. Stack

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind. The existing landing page is ported into this app as the public route.
- **Backend:** Python 3.12 + FastAPI. Pydantic v2 for all schemas.
- **Database:** PostgreSQL with **pgvector**, row-level security on.
  Use pgvector deliberately: it makes the permission predicate an ordinary SQL `WHERE` clause evaluated as part of the ANN query, which is how I3 is satisfied. Do not use an external vector store that forces post-filtering.
- **Object storage:** S3-compatible, signed URLs only.
- **Agents:** Claude Agent SDK (Python) for conversational and bounded-agentic work only.
- **Jobs:** a scheduler for crawls, refreshes, score recomputation and briefs.
- **Tests:** pytest + Playwright. **Type checking and linting must pass in CI from milestone 0.**

Do not add a dependency without telling me why.

---

## 4. Repo layout

```
/apps/web            Next.js — landing (existing), auth, onboarding, dashboard, admin
/services/api        FastAPI — routes, auth, tenancy
  /domain            entities, scopes, roles
  /grounding         context assembler, schema validation, generation logging
  /calculators       ALL deterministic maths. Pure functions. Heavily tested
  /retrieval         scoped vector + relational access. The only path to data
  /connectors        crawler, GA4, GSC, PageSpeed, CRM adapters + normalisers
  /agents            agent definitions, MCP tool servers, skills
  /jobs              scheduled work
/packages/schemas    JSON schemas shared between API and web
/evals               grounding, permission and injection eval suites
/doc                 specification (read-only for you unless I ask)
```

---

## 5. Working agreement

1. One milestone at a time. **Stop at the end of each and wait.**
2. Every milestone ends with: passing tests, a short `MILESTONE-N.md` note describing what exists and what does not, and updated `TASKS.md`.
3. Write the test that proves the invariant *before* the feature it guards, for anything touching permissions or grounding.
4. No mock data in the running app. If data is unavailable, render the honest state.
5. Small commits with clear messages. Do not refactor unrelated code inside a feature commit.
6. If something in the spec turns out to be impractical once you're in the code, stop and tell me — do not silently redesign.

---

## 6. Milestones

### M0 — Foundation
Scaffold both apps, Docker Compose for Postgres + pgvector + object storage, migrations, CI running lint + types + tests, health endpoints, structured logging, secret handling.
**Done when:** `docker compose up` gives a running web and API, CI is green.
**I validate:** the stack starts from a clean clone and CI passes.

### M1 — Tenancy, auth, roles
Users, workspaces, **many-to-many user↔workspace** (agency case), memberships, roles, sessions. Postgres RLS. Active workspace resolved server-side per request, never from a client value. Role → scope mapping from doc 06 §2.3 implemented as data, not scattered conditionals.
**Done when:** cross-tenant and cross-workspace access is impossible and there are tests that try and fail.
**I validate:** run the isolation test suite; attempt a workspace switch and confirm session teardown.

### M2 — Landing integration, URL capture, Preview audit
Port the landing page. Capture URL pre-registration. Build the crawler with the **SSRF guard from doc 06 §1.2** — public IPs only, no metadata endpoints, redirects re-validated per hop, size and time caps. Preview audit is brand + performance + technical SEO on the entered domain only: no competitor discovery, no metered APIs, short TTL, nothing persisted to a Brain. Rate limit per IP and per domain with a global daily ceiling.
**Done when:** a URL produces a reduced audit and every SSRF test case is blocked.
**I validate:** enter a URL and see a real audit; run the SSRF suite; confirm no metered API is called.

### M3 — Registration and domain verification
Registration, email verification, then domain verification by DNS TXT or file-at-path (strong) or same-domain email (weak, flags Owner-claim review). Workspace creation is gated on it. Handle: two workspaces claiming one domain, ownership transfer, revocation.
**Done when:** no workspace exists without a verified domain, and Preview data expires.
**I validate:** try to create a workspace for a domain I don't control and fail.

### M4 — Onboarding, persona, scope enforcement
Pass 1 questions (role, department derived, purpose, URL). Persona object as a stored, editable record. Pass 2 questions after the audit. **Onboarding answers are scope-tagged at capture** — deal size and budget are L3, not company-public. Invitations: role set by the inviter, never self-declared.
**Done when:** the role → scope table is enforced at the API layer and a Contributor cannot reach L3 aggregates.
**I validate:** log in as each role and confirm the surface matches doc 06 §2.3.

### M5 — Documents, classification, indexing
Upload with consent capture. Parse PDF/DOCX/PPTX/XLSX. Chunk with source and page retained. Classify scope and department with `classified_by`, `confidence`, `review_state` persisted. **I4 default-deny.** Embed into pgvector with all scope fields on the row. Review queue UI. Handle parse failures, scanned PDFs without OCR, size limits — visibly, never silently.
**Done when:** a low-confidence document lands in L5 and the review queue, and nothing is silently visible.
**I validate:** upload a payroll-like file and confirm it is not workspace-visible until reviewed.

### M6 — The scoped retrieval layer — the security core
The single path to all data, vector and relational. Session-bound identity (I2). Pre-filtered queries (I3). Citations that inherit permissions. The capability-vs-record disclosure rule from doc 06 §4.5.
Build `/evals/permissions` as executable red-team specs: a Contributor attempting L3 Finance; existence-disclosure attempts; retrieval with a spoofed identity argument; cross-workspace retrieval after a switch; cached-result reuse across roles.
**Done when:** every red-team case fails to leak, and the suite runs in CI.
**I validate:** read the red-team suite and add cases; they must all pass.

### M7 — Company Brain and the review gate
Assemble the Brain: crawl facts, onboarding answers, documents, with provenance on everything. Full audit post-verification (adds competitor discovery and keyword data). Review-gate screen showing every inferred fact with its source, editable, plus an assumptions block. Conflict precedence: user-confirmed > connected system > crawl > inference. Brain versioning with diffs on the fact layer.
**Done when:** I can correct a fact and see the version diff, and a later crawl raises a re-confirmation rather than overwriting.
**I validate:** walk the gate, change three facts, confirm they propagate.

### M8 — Grounding layer and calculators
Company Context assembler. `/calculators` as pure, unit-tested functions — scores, deltas, exposure, weighting. Pipeline execution mode: fetch → compute → single model call → schema-validate → render, with retry then Unavailable. The `generation` audit table with input snapshot, calculation trace, prompt version, cost. Per-tenant and per-user token budgets. Per-skill kill switch.
**Done when:** no number in the system originates from a model, and there's a test proving a model-produced number is rejected.
**I validate:** inspect `generation` rows and trace a displayed number back to its inputs.

### M9 — Dashboard shell and the first department
Global shell: director header, score, data ribbon with freshness, gap banner, period selector, global completeness meter. All seven data states (Live, Partial, Locked, Warming, Self-reported, Stale, Unavailable). Then **Marketing end to end** — the widgets from doc 05 §3 that work without integrations.
**Done when:** every state renders correctly and no widget shows a zero for missing data.
**I validate:** disconnect sources one at a time and confirm each tile degrades honestly.

### M10 — Integrations
GA4, Search Console, PageSpeed. **One CRM connector plus the canonical normalisation model from doc 05 §9** — with the field-completeness check at connect time that tells the customer what can and cannot be calculated. Token encryption. Handle revocation and scope downgrade.
**Done when:** connecting GA4 turns Marketing from Partial to Live, and a CRM missing `last_activity_at` disables stale-deal detection with an explanation at connect.
**I validate:** connect a real GA4 property and a real CRM; revoke and watch the degrade.

### M11 — Operations layer
The first-party system of record: projects, milestones, tasks, assignees, cost lines, issues, subcontractors, project documents. **Cross-department fields stored as references, resolved at read time against the caller's scope** (doc 06 §4.13) — a site supervisor sees the project, not the margin. Mobile-responsive capture. Progress derived from milestones. Ops score and the Stale state.
**Done when:** two users on the same project see different fields according to their scope.
**I validate:** create a project as Owner, view it as an Ops contributor.

### M12 — Agents and the assistant
Claude Agent SDK integration. Per-department agents constructed **per request** with session-bound tools. Bounded-agentic and open-agentic modes. Subagent return-path filtering against the end user's scope (doc 06 §4.11). Untrusted-content boundary and action gating (I7). Always-on assistant with citations, honest refusals, per-user rate limits.
Build `/evals/injection`: instructions embedded in a crawled page, in an uploaded PDF, in a CRM field, attempting data exfiltration via an allowed action.
**Done when:** no injection case produces an unconfirmed external action or an out-of-scope read.
**I validate:** read the injection suite, add cases, watch them fail safely.

### M13 — Artifacts, admin, evals
Artifact store with versions, scope inheritance (I6), staleness marking, explicit declassification. Workspace admin: users, roles, integrations, Brain contents, classification queue, audit log. Internal console: tenant health, per-tenant AI spend, skill versions, eval results, schema-failure rates, time-boxed logged impersonation that inherits — never exceeds — the impersonated identity's scope. Full eval harness in CI: grounding, permissions, injection.
**Done when:** CI fails on a grounding, permission or injection regression.
**I validate:** deliberately break a grounding rule and confirm the build fails.

---

## 7. Quality bar

- Every calculator has unit tests including boundary and zero-delta cases.
- Every permission rule has a test that attempts to violate it.
- Every widget has a test per data state.
- No `TODO` or placeholder shipped in a completed milestone.
- Accessibility: WCAG 2.1 AA on all shipped screens.
- No secret in the repo; no customer content in logs.

---

## 8. Out of scope — do not build

Business Simulator · Decision Intelligence · Voice · Board Packs · Meta publishing · a second CRM connector · accounting integration · Arabic localisation · billing beyond a trial flag · anything marked Phase 2 or Phase 3 in doc 05 unless I ask.

If you think something out of scope is required for something in scope, stop and tell me rather than building it.

---

## 9. Start here

Read the six specification documents. Then produce `ARCHITECTURE.md`, `TASKS.md`, and a list of every ambiguity or contradiction you found that needs my decision. **Write no production code until I approve those three.**
