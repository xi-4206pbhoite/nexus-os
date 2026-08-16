# NEXUS OS — Task Breakdown

**Status:** proposal for approval · no production code written yet
Milestones are from doc 07 §6, expanded into concrete tasks. One milestone at a time; I stop at the end of each and wait.

**Legend:** `[ ]` not started · `[~]` in progress · `[x]` done · **⛔** blocked on a decision in `DECISIONS-REQUIRED.md`

---

## M0 — Foundation

✅ **COMPLETE — awaiting validation.** See `MILESTONE-0.md`.
Decisions applied: **ADR 0001** (native, no Docker) · **ADR 0002** (git local only) · **ADR 0003** (local embeddings, 1024d) · **ADR 0004** (pgvector from M5).

- [x] 0.1 `git init` (branch `main`), `.gitignore`, `.gitattributes` (LF)
- [x] 0.2 Restructure `nexus_os_application/web` → `apps/web`; update `.claude/launch.json`; landing page still builds
- [x] 0.3 `services/api` skeleton — FastAPI app, `pyproject.toml`, layout per doc 07 §4
- [x] 0.4a ADRs 0001–0003 recording your decisions (doc 07 §1)
- [x] 0.4b Native setup replacing Compose: `scripts/setup.ps1`, `scripts/ci.ps1`, `.env.example`
- [x] 0.4c `ObjectStore` — interface + filesystem driver with expiring HMAC-signed URLs (12 tests)
- [x] 0.4d `Mailer` — interface + file driver writing `.eml`
- [x] 0.5a Alembic wired; fails with an actionable message when `DATABASE_URL` is absent; `0001` resolves as head
- [x] 0.5b Migration 0001 — `pgcrypto` required; `vector` created if available, `NOTICE` if not (**ADR 0004**).
      **Scoped to extensions only**: `tenant`/`user`/`workspace`/`membership` move to M1, where they are designed
      together with RLS and the role→scope mapping rather than being rewritten immediately
- [x] 0.5c **Applied** migration 0001 — `alembic_version = 0001`, `pgcrypto` present
- [x] 0.5d Local PostgreSQL 17.11 via the EnterpriseDB **binaries zip** (the installer needs UAC even with
      `--extract-only`); loopback only, no service, no admin. `scripts/pg-local.ps1`
- [x] 0.5e `scripts/db-init.ps1` — database, non-superuser `NOBYPASSRLS` app role, extensions, `.env`, migrations.
      Idempotent; will not rotate a password `.env` depends on without `-Rotate`
- [x] 0.11 Hermetic test fixture — the suite no longer reads the developer's `.env`, with a regression guard
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

- [x] 1.1 **Test first** — 12 isolation tests against real PostgreSQL as the real app role. Cross-workspace,
      cross-tenant, targeted read of a known id, count leakage, forged insert/update/delete, pooled-connection
      switch, and both default-deny states. First assertion is that the app role *cannot* bypass RLS
- [x] 1.2 Migration 0002 — `tenant`, `app_user`, `workspace`, `membership`, `user_session`, `persona`,
      `audit_log`; RLS **ENABLEd and FORCEd** on all four workspace-scoped tables
- [x] 1.3 Registration + login — argon2id, HttpOnly `SameSite=Lax` session cookie, double-submit CSRF,
      session fixation prevented by construction (login always mints a fresh token), timing-equalised
      login with an undifferentiated error so it is not a user-enumeration oracle
- [x] 1.4 **Many-to-many user ↔ workspace** — `membership` with unique `(workspace_id, user_id)`
- [x] 1.5 **Active workspace resolved server-side per request** from `user_session`, re-validated against
      current memberships every request. No header, query param or body field can set it
- [x] 1.6 `ScopedSession` + `current_scope` FastAPI dependency
- [x] 1.7 Role → scope mapping **as data** — frozen `ROLE_GRANTS`, doc 06 §2.3 asserted row by row
- [~] 1.8 Workspace switch validates the target against current membership and calls the teardown seam.
      **The seam logs only** — agent sessions (M12) and scope-keyed caches (M6/M8) do not exist yet
- [x] 1.9 `test_retrieval_signatures.py` — walks every public callable in `app.retrieval` and fails the
      build on an identity argument. Includes a self-test proving the guard can fail
- [x] 1.10 `MILESTONE-1.md`
- [x] 1.11 Migration 0003 — narrow `membership_own_rows` SELECT policy so the workspace switcher can list
      the caller's own memberships without widening the isolation policy

**Done when:** cross-tenant and cross-workspace access is impossible, with tests that try and fail.
**You validate:** run the isolation suite; switch workspace and confirm session teardown.
**Invariants:** I2, I5.

---

## M2 — Landing integration, URL capture, Preview audit

✅ **COMPLETE — awaiting validation.** See `MILESTONE-2.md`.

- [x] 2.1 **SSRF corpus first** — 79 cases: schemes, private/reserved/link-local v4 and v6, IPv4-mapped forms,
      hostnames resolving privately, mixed DNS answers, octal/decimal/hex literals, metadata hostnames,
      userinfo, port allowlist, malformed URLs, address pinning, per-hop redirect re-validation
- [x] 2.2 Landing page in `apps/web` with the hero URL-capture form (doc 06 §1's single primary action)
- [x] 2.3 URL captured pre-registration into `preview_session` with a TTL
- [x] 2.4 Crawler with the doc 06 §1.2 guard — resolve-then-pin, redirects followed by hand and
      re-validated per hop, size cap read incrementally (not from `Content-Length`), time and hop caps
- [x] 2.5 Extraction — observation only, no scoring, no interpretation
- [ ] 2.6 PageSpeed Insights ⛔ **D3** — performance scores structural weight only, labelled as not Core Web Vitals
- [x] 2.7 Preview audit = brand + performance + technical SEO on the entered domain only; competitor
      discovery and keyword data held behind verification; 7 categories render as named unlocks, never zero
- [x] 2.8 Rate limits in Postgres — per IP, per domain, global daily ceiling; atomic upsert proven under
      concurrency; `X-Forwarded-For` honoured only from a configured trusted proxy
- [x] 2.9 Test: **no metered API and no model** is reachable from the unauthenticated path (import-graph walk)
- [x] 2.10 `MILESTONE-2.md`
- [ ] 2.11 Preview TTL sweep job — `expires_at` set and indexed; the deleting job needs the scheduler

**Done when:** a URL produces a reduced audit and every SSRF case is blocked. **Both met.**
**You validate:** enter a URL and see a real audit; run the SSRF suite; confirm no metered API is called.

## M3 — Registration and domain verification

✅ **COMPLETE — awaiting validation.** See `MILESTONE-3.md`.

- [~] 3.1 Email verification — tokens hashed, single-use, expiring, superseded on reissue; `FileMailer`
      writes `.eml` in dev (⛔ **D4** production provider). **`POST /auth/register` does not yet send it**
- [x] 3.2 DNS TXT and file-at-path (**strong**); same-domain email (**weak** → sets `owner_claim_review`).
      The file check is SSRF-guarded and address-pinned; redirects refused
- [x] 3.3 Workspace creation gated — `create_workspace_for_claim` is the only path that inserts a workspace
- [x] 3.4 Two workspaces, one domain → first verified wins via the partial unique index; loser gets a
      `disputed` claim record. The `IntegrityError` race is handled, not just the check-then-insert
- [ ] 3.5a Ownership transfer — **not built**
- [x] 3.5b Revocation — `revoke_claim` flags the workspace for review rather than deleting it
- [~] 3.5c Re-verification cadence — `next_check_at` and `claims_due_for_recheck` exist and are tested;
      only the expiry job is scheduled
- [x] 3.6 Preview expiry — hard delete on an hourly sweep, plus `delete_previews_for_domain` as the
      deletion path for a crawled company with no account. Claimed previews are exempt
- [x] 3.7 `MILESTONE-3.md`
- [x] 3.8 APScheduler wired into the app lifespan; in-process limitation recorded in `scheduler.py`

**Done when:** no workspace exists without a verified domain, and Preview data expires. **Both met.**
**You validate:** try to create a workspace for a domain you do not control, and fail.

---

## M4 — Onboarding, persona, scope enforcement

✅ **COMPLETE — awaiting validation.** See `MILESTONE-4.md`. `D5` resolved as **ADR 0005**.

- [x] 4.1 **Test first** — 27 cases attacking the Contributor boundary, plus 13 on the API-layer mapping
- [x] 4.2 Pass 1 catalogue — role · department (derived, confirmable) · purpose · company URL
- [x] 4.3 Pass 2 catalogue — goals · challenges · ideal customer · deal size · budget · brand terms ·
      currency · fiscal year
- [x] 4.4 **Answers scope-tagged at capture** — `average_deal_size` L3 Sales, `monthly_marketing_budget`
      L3 Finance; unknown keys raise rather than default; a CHECK constraint forbids L3 without a department
- [x] 4.5 Persona stored separately and asserted **never** to reach the retrieval predicate — three ways
- [x] 4.6 Invitations carry the role and who set it; acceptance copies it, never supplies it
- [x] 4.7 `brief_recipients` sequenced into a post-invite stage (doc 06 §4.10)
- [x] 4.8 Role → scope enforced at the API layer via `deps_scope`; LOCKED is a 200 rendered state,
      DENY is a 404, and neither leaks a count
- [x] 4.9 `MILESTONE-4.md`
- [ ] 4.10 Onboarding wizard UI and the answer/invitation routes — **not built**; the tables, rules and
      enforcement layer they will use are

**Done when:** the role → scope table is enforced at the API layer and a Contributor cannot reach L3 aggregates. **Met.**
**You validate:** log in as each role and confirm the surface matches doc 06 §2.3.

---

## M5 — Documents, classification, indexing

⛔ **Gate before starting: pgvector must be resolved** (ADR 0004). Three options — Docker + the official
`pgvector/pgvector` image · a hosted Postgres with pgvector · a local build from official source with MSVC.
Supersede ADR 0004 with the choice.

- [ ] 5.0 Migration that **hard-requires** the `vector` extension — this is where absence becomes fatal
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
