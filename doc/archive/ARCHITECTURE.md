# NEXUS OS — Architecture

**Status:** proposal for approval · derived from `doc/01`–`doc/07` · no production code written yet
**Date:** 16 August 2026

---

## 0. How I am reading the specification

Doc 07 §1 sets the precedence. Applied strictly:

| Rule | Effect |
|---|---|
| Doc 07 (build prompt) is the contract | Its stack, repo layout, milestones and invariants override everything |
| Doc 06 beats doc 03 where they conflict | Doc 06 §12 enumerates those conflicts; each is resolved in doc 06's favour below |
| Doc 05 beats doc 01/03 on dashboard and CRM | The built-in CRM in doc 01 §5 M5 is reversed (doc 05 §0, §13) |
| Doc 04 is analysis, not specification | Its flow is superseded by doc 06 §0's six stages; its truth table remains valid |

**Conflicts already resolved by that precedence** (no decision needed from you — recorded so you can object):

1. *"The AI layer never talks directly to source systems"* (doc 03 §1) → replaced by doc 06 §8.3: **the AI cannot produce a number, and cannot reach data outside the caller's scope.** The agent reaches data only through scoped MCP tools wrapping the same calculators and permission layer the pipeline uses.
2. Backend language open (doc 03 §9) → **Python 3.12 + FastAPI** (doc 07 §3).
3. Vector schema has no scope/department columns (doc 03 §2) → schema changes; scope fields are columns on the chunk row so the predicate is part of the ANN query (doc 06 §4.4, doc 07 §3).
4. Onboarding step count 11 (doc 03) / 7 stages (doc 04) / 6 stages (doc 06) → **doc 06 §0, with Pass 1 and Pass 2 questions per §2.5.**
5. Data states "four" (doc 05 §0) → **seven** (doc 06 §7.1, doc 07 M9).
6. Cross-department interlocks vs allowlists → scoped calculators (doc 06 §4.13).
7. Per-person capacity vs k-anonymity → role-gating (doc 06 §4.14).
8. Built-in CRM (doc 01) → external CRM read-model + normalisation (doc 05 §0, §9).

Everything I could **not** resolve this way is in `DECISIONS-REQUIRED.md`. I have invented no resolutions.

---

## 1. The shape of the system

Four layers. The important property is that **layer 3 is the only path to data**, and layer 4 cannot reach past it.

```
┌──────────────────────────────────────────────────────────────────┐
│ 1 · PRESENTATION            apps/web — Next.js App Router        │
│   public landing (built) · auth · onboarding · review gate       │
│   department dashboards · assistant panel · workspace admin      │
└───────────────────────────┬──────────────────────────────────────┘
                            │ session cookie → server-resolved workspace
┌───────────────────────────┴──────────────────────────────────────┐
│ 2 · APPLICATION            services/api — FastAPI                │
│   auth · tenancy · RBAC · ScopedSession construction             │
│   widget resolvers · schema validation · generation logging      │
│   cost accounting · kill switches · rate limits                  │
└──────┬────────────────────────────────────────┬──────────────────┘
       │                                        │
┌──────┴─────────────────────────┐  ┌───────────┴──────────────────┐
│ 3 · SCOPED DATA ACCESS         │  │ 3b · DETERMINISTIC MATHS      │
│   retrieval/ — THE ONLY PATH   │  │   calculators/ — pure funcs   │
│   vector + relational, both    │  │   no IO, no clock, no random  │
│   pre-filtered by scope        │  │   every number in the product │
│   citations inherit permission │  │   originates here             │
└──────┬─────────────────────────┘  └───────────┬──────────────────┘
       │                                        │
┌──────┴────────────────────────────────────────┴──────────────────┐
│ 4 · MODEL                  agents/ — Claude Agent SDK             │
│   pipeline · bounded agentic · open agentic                       │
│   tools constructed PER REQUEST, identity bound at construction    │
│   no shell, no direct connector access, cannot emit a number       │
└───────────────────────────────────────────────────────────────────┘

  connectors/ (crawler, GA4, GSC, PageSpeed, CRM) write normalised
  read-models into Postgres. Agents never call them directly.
```

### Why this shape

The invariants are not features layered on top — they are the reason for the layering.

- **I1** holds because layer 3b is the only producer of numbers and it has no model in it.
- **I2/I3** hold because layer 3 is the only reader, it takes a `ScopedSession` rather than an identity argument, and layer 4 physically cannot bypass it.
- **I8** holds because layer 4 has no shell tool and connectors live in layer 3's dependency graph, not layer 4's.

---

## 2. Repo layout

Repo root is `D:\Projects\NEXUS_OS` — `/doc` already lives there, which fixes it. The landing page I built moves from `nexus_os_application/web` to `apps/web` (doc 07 §4, M2).

```
/apps/web                Next.js — landing (built), auth, onboarding, dashboard, admin
/services/api            FastAPI
  /domain                entities, scopes, roles, ScopedSession
  /grounding             context assembler, schema validation, generation logging
  /calculators           ALL deterministic maths. Pure. No IO
  /retrieval             scoped vector + relational access. The only path to data
  /connectors            crawler, GA4, GSC, PageSpeed, CRM adapters + normalisers
  /agents                agent definitions, MCP tool servers, skills
  /jobs                  scheduled work
  /migrations            alembic
/packages/schemas        JSON Schema, generated from Pydantic, consumed as TS types
/evals                   /grounding /permissions /injection
/doc                     specification — read-only
/doc/adr                 decision records
```

---

## 3. The permission model — the security core

### 3.1 The resolved scope set

Everything hangs off one server-computed object. It is never supplied by the client and never appears in a model context.

```python
@dataclass(frozen=True)
class ScopedSession:
    user_id: UUID
    workspace_id: UUID          # resolved server-side per request, never from client
    tenant_id: UUID
    role: Role
    departments: frozenset[Department]   # L3 reach
    max_scope: Scope                     # L1..L5 ceiling
    contributor_restricted: bool         # excludes dept-wide aggregates + others' records
    named_l4_item_ids: frozenset[UUID]   # L4 is reachable ONLY by being named
    is_executive_surface: bool
    def cache_key(self) -> str: ...      # I5 — every cache keyed by this, not tenant
```

Constructed once per request in a FastAPI dependency. Passed explicitly into every retrieval call and every widget resolver. **No function in `retrieval/` accepts a `user_id`, and none is reachable without a `ScopedSession`.** A lint rule and a test enforce it.

### 3.2 Role → scope, as data

Doc 06 §2.3 becomes a table in the database plus a frozen Python mapping, not scattered conditionals (doc 07 M1):

| Role | L1 | L2 | L3 | L4 | L5 | Executive |
|---|---|---|---|---|---|---|
| Owner | ✓ | ✓ | all depts | named only | own | ✓ |
| Executive / GM | ✓ | ✓ | all depts | named only | own | ✓ |
| Department Manager | ✓ | ✓ | **own dept** | named only | own | ✗ |
| Contributor | ✓ | ✓ | **own dept, restricted** | ✗ | own | ✗ |
| Viewer | ✓ | ✓ | **✗** | ✗ | own | ✗ |
| External / Client | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

The lattice is monotonic. L4 is not role-reachable. Department is derived from role, Owner-overridable.

> **Consequence I want acknowledged:** a Department Manager's portal is **six directors, not seven** — no Chief of Staff page, no Morning Brief, no composite score. Doc 06 §2.4 recommends this and doc 05 §1's "seven equal directors" is wrong for every non-executive user. See `DECISIONS-REQUIRED.md` D6.

### 3.3 Filter before search — both paths

**Vector (pgvector).** Scope fields are columns on the chunk row, so the predicate is part of the ANN query:

```sql
SELECT id, content, source_doc_id, source_page
FROM chunk
WHERE workspace_id = :ws
  AND (
        scope IN ('L1','L2')
     OR (scope = 'L3' AND department && :depts AND NOT (:restricted AND is_dept_aggregate))
     OR (scope = 'L4' AND id = ANY(:named_l4))
     OR (scope = 'L5' AND owner_user_id = :uid)
      )
  AND review_state != 'quarantined'
ORDER BY embedding <=> :q
LIMIT :k;
```

Filtered ANN degrades recall — a known pgvector characteristic at high filter selectivity. **This needs a measured spike before M6 relies on it** (doc 06 §12); mitigation is HNSW with iterative index scan, falling back to partial indexes per scope. Tracked as task M5.7.

**Relational.** RLS gives tenant isolation only (doc 06 §4.7). Every operational table additionally carries `department` and `sensitivity`, and every repository read applies the same predicate. A widget resolver that cannot satisfy its inputs inside the caller's scope returns **Locked** — it never computes over hidden rows and returns just the total.

### 3.4 Reconciling "pure calculators" with "calculators receive the scope set"

Doc 07 §4 says `/calculators` are pure functions; doc 06 §4.7 says every calculator receives the resolved scope set and applies it in the query. Both hold, split across two objects:

- `retrieval/` — takes `ScopedSession`, does the IO, applies the predicate, returns typed inputs **or** a `Locked(reason)` sentinel.
- `calculators/` — pure. Takes those typed inputs, returns `(value, CalculationTrace)`. No IO, no clock, no randomness. Trivially unit-testable, which is the point: these produce every number a user sees.
- A thin **widget resolver** in the application layer composes the two and maps `Locked`/`Warming`/`Stale` to render states.

### 3.5 Derived artifacts and caches

- **I6** — an artifact's scope is `max(scope of every input)`, with inputs recorded. Declassification is an explicit logged act with a named actor, never a side effect of sharing.
- **I5** — generations, health scores, `score_history` rows and scheduled briefs are keyed by `ScopedSession.cache_key()`. Without this, "role changes take effect immediately" is false for every cached surface.
- The morning brief is **generated per recipient**, never once and broadcast (doc 06 §4.10). Recipients must be workspace users.

### 3.6 Capability existence vs record existence

Encoded as two distinct API response types so it cannot be got wrong by accident (doc 06 §4.5):

- `Locked(capability, required_source, required_role)` — disclosable. *"Requires Finance access."*
- Filtered results — return nothing. Never counts, titles or metadata. *"There are 3 documents you can't see"* is a leak.

---

## 4. Untrusted content boundary (I7)

Every byte from a crawl, a document, a connector payload or screen context passes through one function before it can reach a model context:

```python
def wrap_untrusted(source: ProvenanceRef, content: str) -> UntrustedBlock
```

`UntrustedBlock` renders into the prompt inside a labelled delimiter as **data to analyse, never instruction**, and carries a provenance id. A turn whose context contains any `UntrustedBlock` is **tainted**.

**Action gating.** Read tools and write tools are separate sets. Every externally-visible action — email, WhatsApp, CRM write, publish, external share — checks the taint flag and, if set, requires an explicit human confirmation carrying the exact payload. This is a hard rule, not a setting. The assistant defaults to read + draft; send is a distinct capability.

**Detection.** Provenance logged per context block; instruction-like patterns flagged; any agent turn attempting an action inconsistent with its department alerts; repeatedly-flagged documents quarantined.

Screen context gets the same treatment — tile labels may name entities the caller cannot open.

---

## 5. Execution modes

Three, not two (doc 06 §8.1). A binary split does not survive doc 05's surface.

| | Pipeline | Bounded agentic | Open agentic |
|---|---|---|---|
| Used for | Known input list: traffic trend, SEO table, scores, KPI tiles | Variable retrieval: Morning Brief, Proposal Studio, win/loss, bottleneck | Assistant, department directors |
| Shape | fetch → compute → one model call → schema-validate → render | fixed tool set, capped turns and tokens, schema-validated, cached | full loop, per-user rate limited |
| Audit | one `generation` row | one row + every tool call logged | per-turn logging + session record |

**Guaranteed:** every *number* is code-computed and reproducible. Prose is not bit-reproducible at any temperature and I will not claim it is.

### Agent SDK mapping (doc 06 §8.2)

- **Pipeline modules are not skills.** They are ordinary prompt templates called directly — pipeline mode forbids the nondeterministic description-matching that makes a skill a skill.
- **Calculators are MCP tools or direct backend calls — never skill-bundled scripts.** Skill scripts execute via Bash and granting Bash voids every allowlist (**I8**).
- **Tools are constructed per request** with identity closed over (**I2**). Allowlists are a coarse second layer, not the boundary.
- **Subagent returns are filtered against the end user's scope**, not the parent agent's (doc 06 §4.11). A Finance subagent returning "margin 34%" into a Chief of Staff context is a leak unless filtered on the return path.
- **Hooks are defence in depth only** (doc 06 §4.4 rule 4). PreToolUse asserts the scope invariant, PostToolUse logs. Schema validation, retry and cost accounting live in the application layer, because a hook is per-process and any scheduled job or retry worker would bypass it.

---

## 6. Data model — core tables

```
tenant ─┬─ workspace ─┬─ membership (user × workspace × role × departments)   ← M:N from day one
        │             ├─ domain_verification (method, state, verified_at, evidence)
        │             ├─ persona (per user × workspace)
        │             ├─ brain_version ── fact (key, value, source_ref, confirmed_by, precedence)
        │             ├─ document ── chunk ── embedding      ← scope, department[], owner, sensitivity,
        │             │                                        classified_by, confidence, review_state
        │             ├─ integration (provider, encrypted tokens, scopes, field_completeness)
        │             ├─ crm_deal_normalised  (§9 canonical model — read-model, not system of record)
        │             ├─ project ── milestone ── task            ← the ONLY first-party system of record
        │             │      ├─ cost_line, issue, subcontractor, project_document
        │             │      └─ cross-dept fields stored as REFERENCES, resolved at read time (I3, doc 06 §4.13)
        │             ├─ artifact (version, scope = max(inputs), provenance, generation_ref, stale)
        │             ├─ score_history (department, score, delta, period, scope_key)   ← I5
        │             ├─ generation (module, prompt_version, input_snapshot, calculation_trace, cost)  ← I9
        │             └─ audit_log (actor, action, target, reason, at)
        └─ user
```

Two tables carry disproportionate weight: **`generation`** is what lets any card answer *"why are you telling me this?"*, and **`chunk`** is where a classification mistake becomes a permanent silent breach — hence **I4 default-deny**.

`generation.input_snapshot` is a second copy of customer content. It inherits its inputs' scope tag and retention, and is included in export and deletion (doc 06 §9).

---

## 7. Render states (doc 06 §7.1)

Seven. **Never a zero, never a blank** (I10).

| State | Meaning |
|---|---|
| **Live** | All inputs present and fresh |
| **Partial** | Some inputs; scope reduced and labelled ("4 of 6 scored") |
| **Locked** | Source not connected — names the unlock, is a call to action |
| **Warming** | Connected, insufficient history — "available from [date]" |
| **Self-reported** | Typed by a user; persistently marked; never silently mixed with API-sourced |
| **Stale** | Was Live, source stopped updating — "was 78, no data for 11 days" |
| **Unavailable** | Schema validation failed after retry, kill switch, or provider down. Nothing the user can do |

Composite score always shows its denominator, out of **six** scoreable departments, never seven (doc 05 §10).

---

## 8. Dependencies I intend to add

Doc 07 §3: *"Do not add a dependency without telling me why."* Complete list, nothing else without asking.

**Backend** — `fastapi`, `uvicorn`, `pydantic` v2, `sqlalchemy` 2 + `alembic` (migrations are a doc 07 M0 requirement), `asyncpg`, `pgvector`, `argon2-cffi` (password hashing), `itsdangerous` (signed session cookies), `httpx` (connectors + crawler), `beautifulsoup4` + `lxml` (crawl extraction), `tenacity` (retry), `structlog` (structured logging, M0), `claude-agent-sdk`, `boto3` (S3-compatible), `apscheduler` (scheduler), `pytest` + `pytest-asyncio`, `ruff`, `mypy`.

**Document parsing (M5)** — `pypdf`, `python-docx`, `python-pptx`, `openpyxl`. No OCR: scanned PDFs must fail **visibly**, per doc 07 M5.

**Frontend** — already has `next`, `react`, `tailwindcss`, `framer-motion`. Adding at M1: `@tanstack/react-query` (server state) and `zod` (runtime validation of API responses against `/packages/schemas`).

**Embeddings** — `fastembed` running `intfloat/multilingual-e5-large` at 1024 dimensions, locally on CPU (ADR 0003). No API key, no per-token cost, and customer text never leaves the infrastructure — which makes the doc 01 §6 training commitment structurally true for the embedding path rather than only contractually true. Chosen over `sentence-transformers` because it uses ONNX and avoids a >2 GB PyTorch dependency, which matters for a native install.

**Infrastructure** — none, per **ADR 0001** (no Docker). Each Compose service is replaced by a driver behind an interface, so the production shape survives:

| Doc 07 §3 | Local | Interface |
|---|---|---|
| PostgreSQL + pgvector | free hosted instance (Supabase / Neon) | `DATABASE_URL` |
| S3-compatible object storage | filesystem under `.storage/` | `ObjectStore` |
| Email (M3) | `.eml` files under `.mail/` | `Mailer` |

`FilesystemObjectStore` issues short-lived HMAC-signed local URLs, so the signed-URL requirement is exercised from M0 rather than appearing for the first time at deployment.

**Deliberately not adding:** Redis (rate limits and job state go in Postgres until there is a measured need — fewer moving parts, and more so without Compose), Celery/arq (APScheduler suffices for the current job set), any external vector store (doc 07 §3 forbids it — post-filtering would break I3), PyTorch (see embeddings above).

---

## 9. Testing and CI

Doc 07 §5.3: *write the test that proves the invariant before the feature it guards*, for anything touching permissions or grounding. From M0, CI runs `ruff` + `mypy` + `pytest` on the API and `tsc` + `eslint` + `next build` on the web app, and fails the build on any of them.

Three eval suites, executable red-team specs, in CI from the milestone that introduces them:

- `/evals/permissions` (M6) — Contributor reaching L3 Finance · existence-disclosure · spoofed identity argument · cross-workspace retrieval after a switch · cached-result reuse across roles.
- `/evals/injection` (M12) — instructions in a crawled page, in an uploaded PDF, in a CRM field, exfiltration via an allowed action.
- `/evals/grounding` (M8) — a model-produced number must be rejected; a zero delta must report unchanged; a missing input must render its named state.

**M13 done-when is that CI fails on a regression in any of the three.**

---

## 10. Not being built (doc 07 §8)

Business Simulator · Decision Intelligence · Voice · Board Packs · Meta publishing · second CRM connector · accounting integration · Arabic · billing beyond a trial flag · anything Phase 2/3 in doc 05.

**Two consequences worth stating plainly before you approve:**

1. **Accounting is out of scope, and doc 05 §5 says the Finance Director is *entirely* gated on that one connection.** So the Finance Director ships as a fully Locked page — correct per I10, but it is seven widgets of "connect accounting" and no working surface. Chart-of-accounts mapping and budget entry (doc 05 §5) also fall away with it.
2. **The milestones cover Marketing (M9) and Operations (M11) only.** Chief of Staff, Sales, Finance, HR and Strategy have no milestone. Combined with the Phase 2/3 exclusions, MVP is: audit + Company Brain + Marketing + Operations + assistant. That may well be intended — but doc 05 specifies seven directors and I want it confirmed rather than assumed. See `DECISIONS-REQUIRED.md` D7.
