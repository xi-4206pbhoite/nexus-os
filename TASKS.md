# NEXUS OS — Task Breakdown

**Status:** proposal for approval · no production code written yet
Milestones are from doc 07 §6, expanded into concrete tasks. One milestone at a time; I stop at the end of each and wait.

**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done · **⛔** blocked on a decision in `DECISIONS-REQUIRED.md`

---

## M0 — Foundation

Decisions applied: **ADR 0001** (native, no Docker) · **ADR 0002** (git local only) · **ADR 0003** (local embeddings, 1024d).
⛔ One task remains: **applying** migration 0001, which needs a `DATABASE_URL` for a pgvector-enabled Postgres.

- [x] 0.1 `git init` (branch `main`), `.gitignore`, `.gitattributes` (LF)
- [x] 0.2 Restructure `nexus_os_application/web` → `apps/web`; update `.claude/launch.json`; landing page still builds
- [x] 0.3 `services/api` skeleton — FastAPI app, `pyproject.toml`, layout per doc 07 §4
- [x] 0.4a ADRs 0001–0003 recording your decisions (doc 07 §1)
- [x] 0.4b Native setup replacing Compose: `scripts/setup.ps1`, `scripts/ci.ps1`, `.env.example`
- [x] 0.4c `ObjectStore` — interface + filesystem driver with expiring HMAC-signed URLs (12 tests)
- [x] 0.4d `Mailer` — interface + file driver writing `.eml`
- [x] 0.5a Alembic wired; fails with an actionable message when `DATABASE_URL` is absent; `0001` resolves as head
- [x] 0.5b Migration 0001 — `vector` + `pgcrypto` extensions, with a guard that raises if pgvector is unavailable.
      **Scoped to extensions only**: `tenant`/`user`/`workspace`/`membership` move to M1, where they are designed
      together with RLS and the role→scope mapping rather than being rewritten immediately
- [ ] 0.5c **Apply** migration 0001 against a real database ⛔ needs `NEXUS_DATABASE_URL`
- [x] 0.6 Config and secrets — pydantic-settings, `.env` gitignored, no usable default for any secret
- [x] 0.7 `structlog` JSON logging with request id; secret redaction **and** a hard refusal to log customer content
- [x] 0.8 `/health` (liveness, touches nothing) · `/health/ready` (per-dependency, asserts pgvector is present, leaks
      no DSN on error) · web `/api/health` reporting API reachability as a separate field
- [x] 0.9a CI workflow committed (`ruff` · `ruff format` · `mypy --strict` · `pytest` · `tsc` · `eslint` · `next build` · gitleaks)
- [x] 0.9b `scripts/ci.ps1` runs the identical gate locally — the real gate until a remote exists (ADR 0002)
- [x] 0.10 `MILESTONE-0.md`

**Done when** *(amended by ADR 0001)*: `scripts/setup.ps1` prepares the stack from a clean clone; API and web both start; `/health` returns ok and `/health/ready` reports every dependency honestly; `scripts/ci.ps1` is green.
**Status:** all of the above verified. Outstanding: 0.5c, and `/health/ready` returning `ok` for the database rather than `unconfigured`.
**You validate:** clean clone → `.\scripts\setup.ps1` → start both → hit both health endpoints → `.\scripts\ci.ps1` passes.

---

## M1 — Tenancy, auth, roles

- [ ] 1.1 **Test first:** cross-tenant and cross-workspace read attempts, expected to fail (doc 07 §5.3)
- [ ] 1.2 Migration: `session`, `persona`, `audit_log`; RLS policies on every tenant-scoped table
- [ ] 1.3 Registration + login — argon2id, signed HttpOnly session cookie, CSRF, session fixation prevention
- [ ] 1.4 **Many-to-many user ↔ workspace** from day one (agency case), even though the agency UI ships later
- [ ] 1.5 **Active workspace resolved server-side per request**, never from a client value — a `X-Workspace` header is untrusted input
- [ ] 1.6 `ScopedSession` construction as a FastAPI dependency (ARCHITECTURE §3.1)
- [ ] 1.7 Role → scope mapping **as data** (table + frozen mapping), not scattered conditionals — doc 06 §2.3
- [ ] 1.8 Workspace switch tears down agent sessions and invalidates scope-keyed caches (doc 06 §2.1)
- [ ] 1.9 Lint rule + test: **nothing in `retrieval/` accepts a `user_id`** (guards I2 before the code it guards exists)
- [ ] 1.10 `MILESTONE-1.md`

**Done when:** cross-tenant and cross-workspace access is impossible, with tests that try and fail.
**You validate:** run the isolation suite; switch workspace and confirm session teardown.
**Invariants:** I2, I5.

---

## M2 — Landing integration, URL capture, Preview audit

- [ ] 2.1 **Test first:** the SSRF corpus — `127.0.0.1`, `169.254.169.254`, `[::1]`, `10./172.16./192.168.`, `file://`, `gopher://`, DNS-rebinding, redirect-to-private, oversized body, slowloris
- [ ] 2.2 Port landing page into `apps/web` as the public route (mostly done in 0.2; wire the URL capture form)
- [ ] 2.3 URL capture pre-registration → `preview_session` row with short TTL (⛔ **D9** — TTL value)
- [ ] 2.4 Crawler with the **doc 06 §1.2 SSRF guard** — resolve-then-connect, public IPs only, no metadata endpoints, **redirects re-validated per hop**, size and time caps, `robots.txt` respected
- [ ] 2.5 Extraction: services, segments, tone, contacts, locations, languages — every fact carries a `source_ref`
- [ ] 2.6 PageSpeed Insights connector (⛔ **D3** — API key)
- [ ] 2.7 Preview audit = **brand + performance + technical SEO on the entered domain only.** No competitor discovery, no keyword data, no metered API, nothing persisted to a Brain
- [ ] 2.8 Rate limits in Postgres: per IP, per domain, global daily ceiling
- [ ] 2.9 Test: **no metered API is reachable from an unauthenticated path**
- [ ] 2.10 `MILESTONE-2.md`

**Done when:** a URL produces a reduced audit and every SSRF case is blocked.
**You validate:** enter a URL, see a real audit; run the SSRF suite; confirm no metered API called.
**Invariants:** I7 (crawled content wrapped from first contact), I10.

---

## M3 — Registration and domain verification

- [ ] 3.1 Email verification via mailpit in dev (⛔ **D4** — production email provider)
- [ ] 3.2 Domain verification: DNS TXT and file-at-path (**strong**); same-domain email (**weak** → flags Owner-claim review)
- [ ] 3.3 Workspace creation **gated** on verification — no workspace exists without a verified domain
- [ ] 3.4 Two workspaces claiming one domain → first verified wins, second enters claim-dispute
- [ ] 3.5 Ownership transfer; revocation when the verifying method stops resolving; re-verification cadence
- [ ] 3.6 Preview data expiry job + deletion-request path for the crawled company, which has no account (doc 06 §10)
- [ ] 3.7 `MILESTONE-3.md`

**Done when:** no workspace exists without a verified domain; Preview data expires.
**You validate:** try to create a workspace for a domain you do not control, and fail.

---

## M4 — Onboarding, persona, scope enforcement

⛔ **Blocked on D5** (Contributor L3 subset) and **D6** (six-director consequence).

- [ ] 4.1 **Test first:** a Contributor reaching an L3 aggregate, expected to fail
- [ ] 4.2 Pass 1 (signup): role · department (derived, confirmable) · what they want help with · company URL
- [ ] 4.3 Pass 2 (after audit): ranked goals · challenges · ideal customer · average deal size · marketing budget · words to avoid · currency + fiscal year · brief recipients
- [ ] 4.4 **Onboarding answers scope-tagged at capture** — deal size is L3 Sales, budget is L3 Finance, *not* company-public (doc 06 §2.5)
- [ ] 4.5 Persona as a stored, editable record; **no persona field is ever an input to the retrieval predicate** (doc 06 §2.6) — test asserts this
- [ ] 4.6 Invitations: **role set by the inviter, never self-declared at acceptance** (privilege escalation via dropdown)
- [ ] 4.7 Brief-recipients question sequenced **after** team invitation (doc 06 §4.10)
- [ ] 4.8 Role → scope enforced at the API layer, not the UI
- [ ] 4.9 `MILESTONE-4.md`

**Done when:** the role → scope table is enforced at the API layer and a Contributor cannot reach L3 aggregates.
**You validate:** log in as each role; confirm the surface matches doc 06 §2.3.

---

## M5 — Documents, classification, indexing

- [ ] 5.1 **Test first:** a low-confidence document must land L5 + review queue, never workspace-visible (I4)
- [ ] 5.2 Upload with **consent capture** including the right-to-use warranty (doc 06 §5)
- [ ] 5.3 Parse PDF/DOCX/PPTX/XLSX; chunk with **source doc and page retained** (citations depend on it)
- [ ] 5.4 Classify scope + department; persist `classified_by`, `confidence`, `review_state`
- [ ] 5.5 **I4 default-deny** — parse failure, classification failure, or below-threshold confidence → L5 + review queue
- [ ] 5.6 Embed into pgvector with **all scope fields on the row** (doc 03's schema lacks them — doc 06 §12)
- [ ] 5.7 **Spike: filtered-ANN recall at expected cardinality.** HNSW + iterative index scan vs partial indexes per scope. M6 depends on the answer
- [ ] 5.8 Review queue UI; `sensitivity: personal|restricted` requires human confirmation before anyone else can reach it
- [ ] 5.9 Visible failure states: parse failure, **scanned PDF with no OCR**, size limit — never silent
- [ ] 5.10 Superseded documents **re-run classification**, never inherit the old scope
- [ ] 5.11 `MILESTONE-5.md`

**Done when:** a low-confidence document lands in L5 and the review queue, and nothing is silently visible.
**You validate:** upload a payroll-like file; confirm it is not workspace-visible until reviewed.
**Invariants:** I4, I7.

---

## M6 — The scoped retrieval layer — the security core

- [ ] 6.1 `/evals/permissions` as executable red-team specs, **written before the layer**: Contributor → L3 Finance · existence-disclosure · spoofed identity argument · cross-workspace after switch · cached reuse across roles
- [ ] 6.2 Single retrieval path for vector **and** relational; identity session-bound (I2); pre-filtered (I3)
- [ ] 6.3 Citations inherit permissions — only cite what the caller can open
- [ ] 6.4 `Locked(capability, required_source, required_role)` vs filtered-out, as **distinct response types** (doc 06 §4.5)
- [ ] 6.5 Scope-keyed cache layer (I5)
- [ ] 6.6 Role change is immediate for live **and** cached queries; demotion locks prior threads (doc 06 §4.15)
- [ ] 6.7 Suite runs in CI
- [ ] 6.8 `MILESTONE-6.md`

**Done when:** every red-team case fails to leak; suite runs in CI.
**You validate:** read the red-team suite, add cases, all must pass.
**Invariants:** I2, I3, I5.

---

## M7 — Company Brain and the review gate

- [ ] 7.1 Assemble the Brain: crawl facts + onboarding answers + documents, provenance on everything
- [ ] 7.2 Full audit post-verification — adds competitor discovery and keyword data (⛔ **D2** DataForSEO, **D3** Google keys)
- [ ] 7.3 Review-gate screen: every inferred fact, grouped, with source and edit control, plus a distinct **assumptions requiring confirmation** block
- [ ] 7.4 Conflict precedence: user-confirmed > connected system > crawl > inference
- [ ] 7.5 A later crawl contradicting a confirmed fact **raises re-confirmation, never overwrites**
- [ ] 7.6 Brain versioning with diffs **on the fact layer only** — embeddings are content-addressed and superseded (doc 06 §6)
- [ ] 7.7 Artifact staleness marking when grounding facts change
- [ ] 7.8 Single-writer approval; second approver sees the diff since their view loaded
- [ ] 7.9 `MILESTONE-7.md`

**Done when:** you can correct a fact and see the version diff; a later crawl raises re-confirmation.
**You validate:** walk the gate, change three facts, confirm they propagate.

---

## M8 — Grounding layer and calculators

- [ ] 8.1 **Test first:** a model-produced number is rejected by the pipeline (I1)
- [ ] 8.2 Company Context assembler — single code path, no module builds its own context
- [ ] 8.3 `/calculators` — pure, no IO: scores, deltas, exposure, weighting. Unit tests including **boundary and zero-delta** cases
- [ ] 8.4 Pipeline mode: fetch → compute → one model call → schema-validate → retry once → **Unavailable**
- [ ] 8.5 `generation` table: input snapshot, calculation trace, prompt version, cost. Snapshot inherits input scope + retention (doc 06 §9)
- [ ] 8.6 Per-tenant **and per-user** token budgets; exhaustion degrades to Unavailable — never to a cheaper unevaluated model, never to a stale cache
- [ ] 8.7 Per-skill kill switch
- [ ] 8.8 `/evals/grounding` in CI — zero-delta reports unchanged; missing input renders its named state
- [ ] 8.9 `MILESTONE-8.md`

**Done when:** no number originates from a model; a test proves a model-produced number is rejected.
**You validate:** inspect `generation` rows; trace a displayed number back to its inputs.
**Invariants:** I1, I9, I10.

---

## M9 — Dashboard shell and Marketing

- [ ] 9.1 Global shell: director header · score · data ribbon with freshness · gap banner · period selector · **global completeness meter** (⛔ **D8** — capability count)
- [ ] 9.2 All **seven** render states, each with a component test (doc 06 §7.1)
- [ ] 9.3 Composite score always shows its denominator, **out of six**, never seven (doc 05 §10)
- [ ] 9.4 Marketing end to end — the doc 05 §3 widgets that work without integrations: 3.4 Growth Plan · 3.5 Calendar · 3.6 Content Studio · 3.8 Brand Intelligence · market half of 3.7 SEO
- [ ] 9.5 3.1/3.2/3.3 render **Locked** until GA4 lands in M10 — Marketing is **not scoreable without GA4** (doc 05 §3.1); Brand and SEO audit scores must **not** be merged into a Marketing score to manufacture a number
- [ ] 9.6 Week 1 shows a **Baseline**, not a Morning Brief (doc 05 §2.1)
- [ ] 9.7 WCAG 2.1 AA on every shipped screen
- [ ] 9.8 `MILESTONE-9.md`

**Done when:** every state renders correctly; no widget shows a zero for missing data.
**You validate:** disconnect sources one at a time; confirm each tile degrades honestly.
**Invariants:** I10.

---

## M10 — Integrations

⛔ **Blocked on D3** (Google credentials) and **D10** (which CRM).

- [ ] 10.1 Google OAuth; token encryption at rest via KMS-equivalent; never logged
- [ ] 10.2 GA4 Data API; **verify goals/events configured at connect**, warn if absent (doc 05 §3.2)
- [ ] 10.3 Search Console; PageSpeed promoted from Preview
- [ ] 10.4 One CRM connector + the **canonical normalisation model** (doc 05 §9): `stage_canonical`, `last_activity_at`, `loss_reason`, native label retained
- [ ] 10.5 **Field-completeness check at connect** telling the customer what can and cannot be calculated — a CRM with no `last_activity_at` disables stale-deal detection **at connect**, not later via an empty widget
- [ ] 10.6 Read-only scope at MVP; CRM write is a separate, later, heavier permission (doc 05 §4.6)
- [ ] 10.7 Handle revocation and **OAuth scope downgrade returning partial data that looks valid** (doc 06 §10.1)
- [ ] 10.8 `MILESTONE-10.md`

**Done when:** connecting GA4 turns Marketing Partial → Live; a CRM missing `last_activity_at` disables stale-deal detection with an explanation at connect.
**You validate:** connect a real GA4 property and a real CRM; revoke and watch the degrade.

---

## M11 — Operations layer

- [ ] 11.1 **Test first:** two users on one project see different fields per scope
- [ ] 11.2 Entities: project · milestone · task · assignee · cost_line · issue · subcontractor · project_document
- [ ] 11.3 **Cross-department fields stored as references, resolved at read time** against the caller's scope (doc 06 §4.13) — a site supervisor sees the project, not the margin
- [ ] 11.4 Mobile-responsive capture for progress, issues, photos (doc 05 §6c)
- [ ] 11.5 **Progress derived from milestone completion** — ticking a box, not typing a percentage
- [ ] 11.6 Ops score + the **Stale** state when updates stop
- [ ] 11.7 Guided "create your first project" (doc 06 §10) — without it the only first-party source stays empty
- [ ] 11.8 `MILESTONE-11.md`

**Done when:** two users on the same project see different fields according to their scope.
**You validate:** create a project as Owner; view it as an Ops contributor.
**Invariants:** I3, I6.

---

## M12 — Agents and the assistant

- [ ] 12.1 `/evals/injection` **written first**: instructions in a crawled page · in an uploaded PDF · in a CRM field · exfiltration via an allowed action
- [ ] 12.2 Claude Agent SDK; per-department agents constructed **per request** with session-bound tools (I2, doc 06 §4.12)
- [ ] 12.3 Bounded-agentic and open-agentic modes
- [ ] 12.4 **Subagent return-path filtering against the end user's scope**, not the parent's (doc 06 §4.11)
- [ ] 12.5 Untrusted-content boundary + action gating (I7) — no external action from a tainted turn without confirmation showing the exact payload
- [ ] 12.6 Read tools and write tools as separate sets; assistant defaults to read + draft
- [ ] 12.7 Always-on assistant: citations, honest refusals, **per-user** rate limits, company-fact vs general-knowledge separation
- [ ] 12.8 Chief of Staff and Strategy read the **same computed objects** so they cannot contradict each other (doc 06 §7.3)
- [ ] 12.9 **No agent has shell access** — test asserts no Bash tool in any allowlist (I8)
- [ ] 12.10 `MILESTONE-12.md`

**Done when:** no injection case produces an unconfirmed external action or an out-of-scope read.
**You validate:** read the injection suite, add cases, watch them fail safely.
**Invariants:** I2, I7, I8.

---

## M13 — Artifacts, admin, evals

- [ ] 13.1 Artifact store: versions, **scope inheritance `max(inputs)`** (I6), staleness, **explicit logged declassification**
- [ ] 13.2 External sharing of an artifact whose inputs exceed L2 requires confirmation naming what it contains (doc 06 §4.8)
- [ ] 13.3 Workspace admin: users, roles, integrations, Brain contents, classification queue, audit log — **the audit log is itself access-controlled**
- [ ] 13.4 Internal console: tenant health, AI spend per tenant, skill versions, eval results, **schema-failure rates** (the leading indicator of drift)
- [ ] 13.5 Impersonation: time-boxed, reason-logged, **resolves to a specific identity and inherits — never exceeds — its scope**; L4/L5 unreachable through support tooling; visible in the customer's own audit log
- [ ] 13.6 Incident review shows metadata + redacted excerpt; viewing full `input_snapshot` is impersonation-equivalent
- [ ] 13.7 Data export and deletion fan-out: embeddings, cache, generation snapshots, object storage, artifacts
- [ ] 13.8 Full eval harness in CI — grounding, permissions, injection
- [ ] 13.9 `MILESTONE-13.md`

**Done when:** CI fails on a grounding, permission or injection regression.
**You validate:** deliberately break a grounding rule; confirm the build fails.
**Invariants:** all ten.

---

## Cross-cutting, every milestone

- Passing tests · `MILESTONE-N.md` · updated `TASKS.md`
- Invariant tests written **before** the feature, for permissions and grounding
- **No mock data in the running app** — if data is unavailable, render the honest state
- No `TODO` or placeholder in a completed milestone
- WCAG 2.1 AA on shipped screens
- No secret in the repo; no customer content in logs
- Small commits; no unrelated refactors inside a feature commit
