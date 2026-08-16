# NEXUS OS — User Journey & System Design

**From landing page to a working department dashboard, and the system behaviour behind each step**
Version 1.1 · 16 August 2026

> Version 1.1 incorporates a security and consistency review. The permission model (§4), the untrusted-content boundary (§5) and the agent architecture (§8) changed substantially from v1.0. Section 12 records the contradictions this document creates with docs 03–05.

---

## 0. The journey as specified

| Stage | Journey steps | What happens |
|---|---|---|
| **A · Acquire** | 1–2 | Landing page → register / login |
| **B · Identify** | 3, 4, 8 | Individual or company · role · purpose · company URL → account persona defined |
| **C · Supply** | 5 | Upload resources · connect tools |
| **D · Analyse** | 6, 7, 9 | Analysis runs · Company Brain built with role and department scoping · public knowledge layered on |
| **E · Confirm** | 10, 11 | User reviews what NEXUS inferred · approves |
| **F · Operate** | 12–17 | Department dashboard · insights per tab · configure prompts where data is missing · always-on assistant · document upload to artifacts · ask questions of own data |

Plus three system-wide commitments: an **admin panel**, a **specialised agent per department**, and a **skill-based agent framework** on the Claude Agent SDK with a Python backend.

---

## 1. Stage A — Landing, registration, domain verification

**Landing page.** One primary action: *"Analyse my business — enter your website."* The URL is captured before registration and becomes the first fact NEXUS holds.

**Registration.** Name, work email, password or OAuth. Everything else moves to Stage B.

### 1.1 Domain verification

Anyone can type a competitor's URL. Without a check, NEXUS crawls a company the registrant does not own, produces an audit of it, names its competitors, and hands that to a stranger — a competitive-intelligence product sold by accident.

**Preview state.** Before verification the workspace is ephemeral: a **reduced** audit is shown — brand, performance and technical SEO on the entered domain only. **No competitor discovery, no keyword market data, no downloadable output, nothing persisted beyond a short TTL.** The competitor list is the part that has intelligence value about a third party, so it sits behind verification.

**Verification methods, not equivalent.** DNS TXT record or a file at a known path are strong. Email on the domain is weaker — it proves employment, not authority — so it grants workspace creation but flags the account for Owner-claim review if a second person from the same domain registers. Manual approval by support requires documentary evidence and is logged; free-email SMEs are common in this market and this path must exist, but it is the social-engineering target and should be treated as one.

**Also required:** re-verification on a cadence, an explicit rule for two workspaces claiming one domain (first verified wins; second enters a claim-dispute flow), an ownership-transfer path, and revocation when the verifying method stops resolving.

### 1.2 Protecting the unauthenticated crawl path

The pre-registration analysis is a server-side fetch of a user-supplied URL, so it carries two risks that must be closed before launch.

**SSRF.** The fetcher must resolve and validate the target before connecting: public IPs only, no cloud metadata endpoints, no private or link-local ranges, no `file://` or non-HTTP schemes, redirect chains re-validated at every hop, response size and time capped. This applies equally to **discovered** competitor URLs, which are influenced by search results and by the model and are therefore not trusted input either.

**Cost amplification.** Metered APIs must never sit on an unauthenticated path. In Preview, PageSpeed and the crawler run under a per-IP and per-domain rate limit with a global daily ceiling; **DataForSEO, Maps and Custom Search run only after verification.** Without this, a script exhausts a paid quota and degrades the product for paying tenants.

---

## 2. Stage B — Account type, roles, scopes, persona

### 2.1 Three account types

| Type | Who | Brain model | Departments |
|---|---|---|---|
| **Individual** | Freelancer, consultant, solo operator | One personal Brain | Reduced set. No department security — they are every department |
| **Company** | The main case | One Company Brain, department-scoped | All seven directors, role-gated |
| **Agency / Partner** | One operator, many client companies | Many Brains, one identity, strict isolation | Per client workspace |

**Model users and workspaces many-to-many from day one**, even if the agency UI ships later.

**Isolation for multi-workspace identities is a specific engineering problem, not a policy.** Session-claim-based row-level security assumes one tenant per session; a workspace switcher breaks that assumption. Required: the active workspace is resolved server-side per request, never from a client-supplied value; every cache key includes workspace; agent sessions are torn down on switch and never reused across workspaces.

**Individual → Company promotion needs a re-scoping gate.** Every chunk in a personal Brain was indexed with no meaningful department scope. Promotion must not silently publish the founder's personal notes to the first hires. On upgrade, all existing content defaults to **L5 (owner-only)** and the user walks a bulk re-classification screen to promote what should be shared. Default-deny, then opt in.

### 2.2 Roles

The first user is the account creator and is Owner — they cannot be scoped to one department. **Every subsequent user's role is set by the inviter, never self-declared at acceptance.** Self-declared role is privilege escalation via dropdown.

### 2.3 Role → scope mapping

This table is the most important artifact in the security model. Scopes are defined in §4.2.

| Role | L1 Company public | L2 Company internal | L3 Department | L4 Restricted | L5 Personal | Executive surface |
|---|---|---|---|---|---|---|
| **Owner** | ✓ | ✓ | All departments | Only if named | Own only | ✓ |
| **Executive / GM** | ✓ | ✓ | All departments | Only if named | Own only | ✓ |
| **Department Manager** | ✓ | ✓ | **Own department only** | Only if named | Own only | ✗ |
| **Contributor** | ✓ | ✓ | **Own department, restricted subset** — excludes department-wide financial aggregates and other people's records | ✗ | Own only | ✗ |
| **Viewer** | ✓ | ✓ | **✗ — no L3** | ✗ | Own only | ✗ |
| **External / Client** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

Three corrections this encodes:

- **The lattice is monotonic.** A Viewer previously reached L3 department detail while being denied less-sensitive L2. Viewers now get L1 and L2 only.
- **Contributor is not the same as Manager.** A junior salesperson should not hold every deal value in the pipeline. Contributor L3 is a restricted subset.
- **L4 is not reachable by role.** It is reachable only by being named on the item, including for the Owner. Otherwise L4 is a UI convention, not a boundary. The Owner may see that L4 content *exists* and may reassign who is named — that act is logged and visible to the named parties.

**Department is derived from role, not chosen at signup**, and the Owner can override per user afterwards.

### 2.4 Executive surface access

Restricting the Executive dashboard to Owner and Executive is the MVP answer to the aggregate problem (§4.6), and it has a cost that must be acknowledged: **for a Department Manager the portal is six directors, not seven** — the Chief of Staff page, and with it the Morning Brief and the composite score, is not visible. That contradicts doc 05's "seven equal directors" premise for every non-executive user.

The alternative, per-metric aggregate rules, is more work and more failure-prone. Recommendation stands, but §12 records the contradiction rather than hiding it.

### 2.5 Questions asked at Stage B

**Pass 1 — at signup:** role · department (derived, confirmable) · what they want help with most · company URL.

**Pass 2 — after the audit is shown:** ranked goals · biggest challenges · ideal customer · average deal size · monthly marketing budget · words to avoid · currency and financial year · brief recipients.

**Onboarding answers carry scope like anything else.** Average deal size and marketing budget are L3 Sales and L3 Finance facts. They are not "company facts" visible to everyone merely because they arrived through a form. Tag them at capture.

### 2.6 The persona object

```
persona {
  role, seniority, department_access[],
  stated_purpose, priority_topics[],
  default_landing_screen,
  communication_style, notification_prefs,
  language, timezone
}
```

The persona shapes what the assistant leads with and how it phrases things. **No persona field is ever an input to the retrieval predicate** — access is resolved from role and scope alone. Conflating presentation preference with authorisation is how access-control bugs get written.

---

## 3. Stage C and D — Supply, analyse, build the Brain

### 3.1 Analysis is continuous, not a step

1. Reduced crawl analysis runs immediately (§1.1 Preview limits apply).
2. After verification, the full audit runs and is shown.
3. Connections and uploads are then requested individually, each naming its unlock.
4. Analysis re-runs incrementally as each source lands.

### 3.2 Pipeline

```
URL → crawl → extract (services, segments, tone, contacts, locations, languages)
            → PageSpeed · Google Business Profile reviews
            → competitor discovery (post-verification)
            → keyword data (post-verification)
            → audit scores, each with evidence
documents  → parse → chunk → classify scope + department → embed → index
integrations → normalise → store read-model → recompute scores → write score_history
```

Every step writes provenance. Nothing enters the Brain without a source reference.

### 3.3 Classification is default-deny

Scope classification decides who can see a chunk, and it is done by a classifier that will sometimes be wrong. One misclassified payroll export is a silent, permanent, workspace-wide breach.

- The chunk record stores `classified_by`, `confidence` and `review_state`.
- **Below a confidence threshold, or on any parse or classification failure, the chunk defaults to L5 — visible only to the uploader** — and appears in a review queue.
- Anything classified `sensitivity: personal | restricted` requires human confirmation before it becomes reachable by anyone else.
- Superseded documents re-run classification; they do not inherit the old scope.

### 3.4 Brain composition

| Layer | Content | Origin |
|---|---|---|
| **Public knowledge** | General world and industry knowledge | The model. Never presented as company fact |
| **Company facts** | Services, market, brand voice, competitors, locations | Crawl + onboarding answers (scoped per §2.5) |
| **Company documents** | Price lists, proposals, policies, drawings, reports | Uploads, RAG-indexed |
| **Operational data** | CRM read-model, GA4, accounting, Ops projects | Connected systems + first-party Ops layer |

---

## 4. The Company Brain permission model

Journey step 7 is one sentence and is the hardest thing in the build.

### 4.1 Chunk record

```
chunk {
  tenant_id, workspace_id, source_doc_id, source_page,
  scope,               // L1–L5
  department[],
  owner_user_id,       // for L5
  sensitivity,         // normal | financial | personal | restricted
  classified_by, confidence, review_state,
  supersedes_id, retention_until,
  created_at, version
}
```

### 4.2 Scopes

| Scope | Contents |
|---|---|
| **L0 Public** | World and industry knowledge — from the model, not retrieved |
| **L1 Company public** | Website content, published material, brand |
| **L2 Company internal** | Strategy, goals, competitor analysis, plans |
| **L3 Department** | Pipeline detail, financial figures, project costs |
| **L4 Restricted** | Payroll, individual performance, M&A, legal |
| **L5 Personal** | A user's own uploads, not shared |

### 4.3 Identity comes from the session, never from a tool argument

If a retrieval tool accepts `user_id` as a parameter, the model fills it in — and the model's context contains crawled competitor pages and uploaded PDFs. A single injected line is then sufficient to request another user's scope.

**Rule: the caller's identity and resolved scope set are bound to the MCP server instance or transport session at construction time, outside the model's reach.** Tools take a query, never an identity. This is the difference between an access control and a suggestion.

### 4.4 The four retrieval rules

1. **Filter before search.** The permission predicate is part of the vector query, not a post-processing pass. Post-filtering leaks through ranking, result counts and latency.
2. **Never disclose the existence of a specific inaccessible record.** See §4.5 for what *may* be disclosed.
3. **Citations inherit permissions.** Only cite sources the caller can open.
4. **Enforcement lives in the data-access layer.** Hooks are defence in depth, not the boundary — a hook is configured per process, so any path that bypasses the orchestrator (a scheduled job, a retry worker, a second service) would be unfiltered.

### 4.5 Capability existence may be disclosed; record existence may not

The zero-data UX depends on naming what is missing — "Connect accounting to unlock Finance" — while the leak rule says never reveal inaccessible content. These are different things and the distinction must be explicit in code:

| Disclosable | Not disclosable |
|---|---|
| A capability exists and is locked | That a specific document, deal or record exists |
| A source type is unconnected | Titles, counts or metadata of filtered results |
| A metric requires a role you lack | The value, or any function of the value |
| A department exists in the workspace | Its contents or aggregates |

"Requires Finance access" is safe. "There are 3 documents you can't see" is not.

### 4.6 Aggregates

The Executive layer aggregates across departments; department scoping resists exactly that.

**MVP:** Executive surface restricted to Owner and Executive (§2.4).

**When that becomes too restrictive:** an aggregate renders only if every component is visible to the caller; otherwise it renders Locked with a capability-level reason. Never silently compute over hidden components and present the result.

### 4.7 The relational path needs the same protection as RAG

Health scores, forecasts, margins and project costs are computed by code reading Postgres, not by vector search. Row-level security gives **tenant** isolation; it does not give **department** isolation over precisely the L3 data that matters most.

**Every operational table carries `department` and `sensitivity`, and every calculator receives the caller's resolved scope set and applies it in the query.** A calculator that cannot satisfy its inputs within the caller's scope returns Locked — it does not compute over data the caller cannot see and return only the total.

### 4.8 Derived artifacts inherit the maximum scope of their inputs

A generated artifact takes `scope = max(scope of every input)` and records those inputs. A proposal grounded in L3 margin data is an L3 artifact; a board pack touching L4 is L4.

**Declassification is an explicit, logged act with a named actor** — never a side effect of clicking share. This matters most for Proposal Studio, which is designed to send Brain-grounded documents to people outside the company. External sharing of an artifact whose inputs exceed L2 requires confirmation that names what it contains.

### 4.9 Caches, precomputed scores and scheduled outputs are permission-keyed

Any cached or precomputed artifact — generations, composite scores, `score_history` rows, nightly briefs — **is keyed by the requesting principal's resolved scope set**, not by tenant alone. Without this, an Owner-triggered composite is served to a Contributor and "role changes take effect immediately" is false for every cached surface.

### 4.10 Scheduled and emailed output

The morning brief is a cross-department composite that leaves the product and cannot be recalled.

- **Recipients must be workspace users**, not free-text addresses. The brief recipient question in onboarding therefore comes *after* team invitation, not before.
- **Scope is re-resolved per recipient at send time**, and each recipient gets only what their current role permits — the brief is generated per recipient, not once and broadcast.
- If a recipient's role no longer permits the composite, they receive their department view instead, or nothing.
- External-address delivery is a separate feature requiring explicit Owner approval, and is out of MVP.

### 4.11 Subagent returns are a scope boundary

A subagent's final message returns into the parent's context. A Finance subagent's conclusion — "margin 34%, two customers are 61% of revenue" — lands verbatim in the Chief of Staff context, and from there into whatever it renders. Context isolation during reasoning does not isolate the return path.

**Rule: subagent returns are scope-tagged and filtered on the return path against the *end user's* scope, not the parent agent's.** If the end user cannot see L3 Finance, a Finance subagent returns a computed, non-disclosing summary or nothing at all. This is the mechanism the "structural isolation" claim depends on, and it must be built explicitly.

### 4.12 Tool allowlists give department isolation, not per-caller scoping

An agent's allowlist is static configuration. The same Marketing Director agent serves an Owner and a Marketing contributor, who must see different Marketing data. Allowlists cannot express that.

**Per-caller scoping is achieved by constructing the agent's tool instances per request, bound to the caller's session identity (§4.3).** Allowlists remain useful as a coarse second layer.

### 4.13 The Operations layer crosses department boundaries by design

Ops projects link to CRM deals and to finance cost lines. Project profitability is Ops cost × Finance revenue. Delivery risk is Ops milestones × deal value. Meanwhile Ops contributors are site staff — the least privileged population in the workspace.

**Rule: the Ops record stores a reference, never a copy, of cross-department values.** Resolution happens at read time against the caller's scope. A site supervisor sees the project, milestones, tasks and issues; the contract value and margin fields render Locked. A project manager with Finance access sees them.

This also resolves the tension with the cross-department interlocks in doc 05 §11: interlocks are computed by **scoped calculators in the data layer**, not by agents reaching across allowlists. The interlock exists; who can see its output depends on the caller.

### 4.14 Small-team anonymity

Suppress people-derived aggregates computed over fewer than three individuals. Note two limits honestly: a manager who knows their own team can difference them out of a larger aggregate, and period selectors allow differencing over time. k-anonymity is a mitigation, not a guarantee — for genuinely sensitive people metrics, restrict by role instead of relying on aggregation.

**This does not conflict with per-person capacity views in Ops**, which are intentionally individual and are gated by role: a manager may see their own team's assignments; nobody sees another department's.

### 4.15 Role change and departure

Query-time evaluation means a role change is immediate for live queries — and, given §4.9, for cached ones too. Two cases need explicit handling:

**Demotion.** Prior conversation threads containing now-restricted data are retained but locked: no re-generation, no export, no search.

**Departure.** Offboarding must resolve L5 chunks (transfer to Owner or delete), owned artifacts, active threads, brief recipient lists, and Ops task assignments — the last of which affects utilisation denominators for the whole department.

---

## 5. Untrusted content and prompt injection

NEXUS ingests text from competitor websites, the customer's own site, and uploaded documents, then puts it in front of agents that can create tasks, draft content, write to a CRM and send messages. **Injection does not need to defeat the retrieval filter — it needs a legitimately scoped agent to take an action.** This is the largest single risk in the design.

**The untrusted-content boundary.** All crawled pages, all document text, all connector payloads and all screen context are wrapped and labelled as data, never as instruction, at every point they enter a model context. Agents are instructed — and evaluated — to treat content inside that boundary as material to analyse, never as directions to follow.

**Action gating.** No externally-visible action executes directly from a turn whose context contains untrusted content. Sending email or WhatsApp, writing to a CRM, publishing, and sharing artifacts externally all require explicit human confirmation showing the exact payload. This is a hard rule, not a preference setting.

**Least privilege on the action side.** Read tools and write tools are separate; write tools live in a small, audited set; the assistant defaults to read plus draft, with send as a distinct capability.

**Detection and containment.** Log the provenance of every context block. Flag content containing instruction-like patterns for review. Alert on any agent turn that attempts an action inconsistent with its department. Quarantine documents that trigger repeated flags.

**Screen context is untrusted too.** The current-screen block passed to the assistant may carry entity labels from tiles the caller cannot open. It gets the same filter as retrieval.

**One more ingestion risk:** a user can upload a third party's confidential material — a competitor's leaked price list — which then becomes citable grounding. Upload consent must state that the customer warrants their right to the content, and the review queue is the practical control.

---

## 6. Stage E — The review gate

One of the strongest ideas in the journey, and it deserves a designed screen.

**Shows:** every inferred fact, grouped, each with its source and an edit control — services, segments, market and languages, brand tone, competitors, audit scores with their evidence — plus a distinct **assumptions requiring confirmation** block.

**Why it matters beyond accuracy:** it is where the user learns NEXUS is grounded rather than guessing, and it converts them from recipient to co-author. It is also the cheapest correction point in the whole system.

**Conflict precedence.** When sources disagree, the order is: user-confirmed fact > connected system > crawl > model inference. A later crawl that contradicts a user-confirmed fact does not overwrite it — it raises a re-confirmation prompt.

**Versioning.** Approval writes a Brain version with a diff. Since analysis is continuous, versioning applies to the **fact layer and the confirmed profile**, not to every embedding — embeddings are content-addressed and superseded, which keeps this affordable.

**Artifact staleness.** An artifact generated against Brain v3 whose grounding facts changed in v4 is marked stale and offers regeneration. It does not silently keep displaying citations to superseded facts.

**Re-review triggers:** a major source connecting, a bulk document upload, a detected site relaunch, a monthly cadence.

**Concurrency:** approval is a single-writer operation; a second approver sees the diff since their view loaded.

---

## 7. Stage F — Dashboard, assistant, artifacts

### 7.1 Rendering states

Doc 05 §0's states, corrected to five and extended by two:

**Live · Partial · Locked · Warming · Self-reported**, plus:

- **Stale** — was Live, its source has stopped updating. Critical for the Ops layer, whose score depends on people continuing to update it. "Was 78, no data for 11 days" is honest; silently holding 78 is not.
- **Unavailable** — schema validation failed after retry, a skill is disabled by kill switch, or an upstream provider is down. Distinct from Locked: nothing the user can do, and it says so.

### 7.2 The always-on assistant

| Property | Specification |
|---|---|
| **Presence** | Persistent panel on every screen |
| **Scope** | Brain filtered by the caller's session-bound scope (§4.3) + L0 |
| **Context** | Current screen, period, selected entity — filtered per §5 |
| **Grounding** | Cites sources; says "I don't have that — connect X" rather than guessing |
| **Knowledge separation** | Company fact and general knowledge must read differently. "Your margin is 34%" and "sector margins are typically around 30%" are different claims |
| **Actions** | Create tasks, draft content, generate documents, navigate — logged. **External actions require confirmation (§5) and carry an undo window where the channel permits; where it does not — a sent message — the confirmation is the control** |
| **Refusals** | No quantified forecast without the inputs to compute one |

**L0 is enforced by prompt, and prompt enforcement is weak** — this is the one scope that cannot be filtered by a query predicate, because parametric knowledge is not retrieved content. Mitigations: require citations for company-fact claims so uncited claims are visibly general; eval specifically for general knowledge being presented as company fact; and treat this as a known residual risk rather than a solved problem.

**Rate limiting is per user, not only per tenant** — otherwise one user exhausts the workspace budget for everyone.

### 7.3 Department agents

Seven directors, each with its own prompt, skills and tool set, constructed **per request** and bound to the caller's identity (§4.12).

Chief of Staff and Strategy read from the **same computed objects** so they cannot contradict each other — a constraint from doc 05 §8 that two independent agent loops would otherwise break.

### 7.4 Documents, artifacts, and "will this work?"

**Artifacts** hold uploads and generated outputs with version history, scope (§4.8), provenance, and a link to the generation record.

**Data pasted into chat is self-reported.** The system asks: use once, or save to the Brain? Only explicit promotion writes it, tagged self-reported, attributed and dated. **A per-user "always save" default is not offered** — it would reintroduce exactly the silent absorption this rule prevents. Note honestly that "use once" still persists in the transcript and in the generation record; it is excluded from retrieval, not from storage.

**"Will it work?"** is a prediction request. The assistant restates what it knows, reasons qualitatively about the mechanism, cites the company's own comparable history where it exists, gives a directional view — and refuses a specific percentage unless the deterministic model has the inputs. It then names the two or three data points that would let it answer properly. That refusal is the product working, and the UI presents it as helpful.

---

## 8. AI execution architecture

### 8.1 Three execution modes

A binary pipeline/agentic split does not survive contact with doc 05's surface — roughly ten specified widgets need variable retrieval or variable tool selection and cannot be fixed pipelines.

| | **Pipeline** | **Bounded agentic** | **Open agentic** |
|---|---|---|---|
| **Used for** | Widgets with a known input list: traffic trend, SEO table, health scores, KPI tiles | Widgets needing variable retrieval or conditional inputs: Morning Brief, Today's Priorities, Proposal Studio, Competitor War Room, Opportunity Radar, win/loss, bottleneck analysis, expansion analysis, bid/no-bid | Assistant conversation, department directors, investigation |
| **Shape** | Fetch → compute in code → one model call → schema-validate → render | Fixed tool set, capped turns, capped tokens, schema-validated result, cached | Full loop, per-user rate limited |
| **Reproducibility** | **Numbers** are deterministic because code computes them; prose is not | Same guarantee on numbers | Same guarantee on numbers |
| **Audit** | One generation row | One generation row summarising the turn set, with every tool call logged | Per-turn logging, session-level record |

**What is actually guaranteed:** every *number* is computed by code and is reproducible. Prose is not bit-reproducible at any temperature and the specification should not claim otherwise.

### 8.2 Mapping to the Claude Agent SDK — corrected

| Concept | Reality | How NEXUS uses it |
|---|---|---|
| **Skills** | Model-invoked instruction bundles, selected by description matching inside a loop. Frontmatter is name/description; the SDK does not read or enforce extra files placed alongside | Used in the two agentic modes. **Pipeline modules are not skills** — they are ordinary prompt templates called directly, because pipeline mode forbids the nondeterministic selection that makes a skill a skill. Schemas, grounding rules and eval cases live beside each skill by *our* convention, enforced by *our* harness |
| **Agents / subagents** | Definitions with tool allowlists, fixed at definition time unless constructed programmatically. Subagent output returns into the parent context | One per director, constructed per request with session-bound tools (§4.12). Return path filtered per §4.11. Nesting is one level — deeper composition (bid/no-bid spanning three departments) is orchestrated in our code, not by the SDK |
| **Calculators** | **Not "scripts."** Skill-bundled scripts execute via Bash, and granting Bash to a department agent voids every allowlist claim | Deterministic calculators are exposed as **MCP tools** or called directly by the backend. **No agent has shell access** |
| **Hooks** | PreToolUse, PostToolUse, UserPromptSubmit, SessionStart/End, Stop, SubagentStop, PreCompact, Notification. There is no post-generation hook; PostToolUse fires on tool results, not final output | Defence in depth: PreToolUse asserts the scope invariant, PostToolUse logs. **Schema validation, retry and cost accounting live in the application layer**, where doc 03 already places them |
| **MCP tools** | Server instances can close over session state | Every data-access tool is constructed with the caller's identity bound in (§4.3) |

### 8.3 Where the AI meets the data — reconciling with doc 03

Doc 03 states that the AI layer never talks to source systems and only receives a prepared data block. That holds for pipeline mode and is what makes numbers auditable. It cannot hold literally for agentic mode, where the agent chooses what to fetch.

**Reconciliation:** the agent never touches a source system directly. It calls scoped MCP tools that wrap the same normalisers, the same calculators and the same permission layer the pipeline uses. The invariant preserved is not "the AI cannot fetch" but **"the AI cannot produce a number, and cannot reach data outside the caller's scope."** Doc 03 §1 should be amended to that wording.

### 8.4 Backend

Python (FastAPI) hosting the Agent SDK runtime, the grounding layer, the calculator library, connector adapters and normalisers, the scheduler, and the eval harness.

Guardrails from day one: per-tenant **and** per-user token budgets · permission-keyed caching (§4.9) · cheap-model routing where evals allow · latency budgets per mode · a per-skill kill switch · defined degradation behaviour when a budget is exhausted (degrade to Unavailable with an explanation, never to a cheaper model that has not passed that module's eval, never to a stale cache).

### 8.5 Evals

Roughly half the offerings in doc 05 have no module in the supplied prompt library. Every skill ships with its own grounding rule and eval cases. Add injection-resistance cases (§5) and permission-boundary cases (§4) to the harness — those are the two failure classes that cause real damage.

---

## 9. Admin

**Workspace admin (the customer's).** Users, roles, department access, integrations and health, Brain contents and versions, the classification review queue (§3.3), artifact retention, billing, and an audit log — which is itself access-controlled, since it records queries and document titles.

**NEXUS internal console (ours).** Tenant health and activation · AI spend per tenant with alerting · skill and prompt versioning with staged rollout · eval results · schema-validation failure rates, the leading indicator of drift · integration error rates · feature flags · **time-boxed, reason-logged impersonation visible in the customer's own audit log**.

**Two rules that were previously in tension:**

- **Impersonation resolves to a specific identity** and inherits that identity's scope. It never grants a superset. L4 and L5 are not reachable through support tooling; access to them requires the customer to grant it explicitly, per incident.
- **Incident review does not expose customer content by default.** A flagged generation shows metadata, the rule that fired, and a redacted excerpt. Viewing the full `input_snapshot` is an impersonation-equivalent act: logged, reason-required, customer-visible. Otherwise "no internal user reads customer documents without an impersonation session" is not true.

**`generation.input_snapshot` is a second copy of customer content.** It carries the same scope tag as its inputs, the same retention policy, and is included in export and deletion.

---

## 10. Gaps in the journey

| Gap | Placement |
|---|---|
| **Billing and trial** | Trial at workspace creation; paywall position is an open decision |
| **Team invitation** | Right after the review gate, framed as an unlock — and **before** the brief-recipients question (§4.10) |
| **Ops adoption** | A guided "create your first project" step once the dashboard lands; without it the only first-party source stays empty |
| **Consent for document indexing** | At upload, including the right-to-use warranty (§5) |
| **Data export and deletion** | Must fan out to embeddings, cache, generation snapshots, object storage and artifacts |
| **Preview-data retention** | Crawl data for unverified domains: short TTL, and a deletion request path for the crawled company, which has no account |
| **MFA / SSO / SCIM** | Absent from every document. A product holding accounting and payroll data will be asked for these in the first enterprise security review |

### 10.1 Failure modes needing designed states

Schema validation failing after retry · token budget exhausted mid-conversation · kill switch on a skill a widget depends on · upstream API outage or quota exhaustion mid-audit · model provider outage while the assistant is on every screen · conflicting facts between sources (§6) · superseded price lists cited in client-facing proposals — **the highest-reputational-damage failure in the product** · document parse failures including scanned PDFs with no OCR · site relaunch invalidating all crawl facts at once · currency or fiscal-year change after data exists · user offboarding (§4.15) · tenant deletion fan-out · OAuth scope *downgrade* returning partial data that looks valid · crawler traps and Cloudflare blocks · Ops adoption decay → the new Stale state (§7.1).

---

## 11. Open decisions

Items previously stated as settled in the body have been removed from this list. What remains is genuinely open.

1. **Individual tier at MVP**, or Company-only to launch?
2. **Agency UI timing** — model is agreed, interface is not scheduled.
3. **Trial length and paywall position** — before or after the review gate?
4. **Which department agents ship first** — Marketing and Sales need least data; Operations produces the most.
5. **Contributor L3 subset** — exactly which department data a contributor sees needs defining per department with a design partner.
6. **Per-metric aggregate rules** — when to move off Owner-only Executive access (§2.4).
7. **k-anonymity threshold** — 3 is conventional; confirm against real team sizes.

---

## 12. Contradictions this document creates

Recorded rather than hidden. Each needs a decision before build.

| With | Contradiction |
|---|---|
| **Doc 03 §1** | "The AI layer never talks directly to source systems." Agentic mode requires scoped tool access. Amend to the invariant in §8.3 |
| **Doc 03 §2, §9** | Backend language listed as open (Python or .NET); this document assumes Python for the Agent SDK. Record the decision |
| **Doc 03 §2** | The vector store schema carries only tenant, document and page — **no scope or department fields**. §4.4's pre-filter cannot be executed against it. Schema must change, and pre-filter recall at this cardinality needs a spike before it is relied on |
| **Doc 03 §5, §9** | GPT is in the provider routing decision (images, voice, cheap high-volume) but absent from this document's agent architecture. Non-Claude models are not native to the Agent SDK loop — decide whether they sit outside it as pipeline calls |
| **Doc 03 §1, §6** | Still specifies an 11-step onboarding wizard, and its Phase 1 estimate is costed against it. Doc 04 proposed seven stages, this document six. Re-cost |
| **Doc 04 §6** | "6 of 21 capabilities"; doc 05 says "8 of 24". Reconcile the capability count |
| **Doc 05 §0** | Says "four states" then lists five; this document defines seven (§7.1) |
| **Doc 05 §0, §1** | "Seven equal AI directors" with a consistent surface — but a Department Manager sees six (§2.4) |
| **Doc 05 §11** | Cross-department interlocks vs. per-department tool allowlists. Resolved in §4.13 by moving interlocks into scoped calculators; doc 05 should reference that |
| **Doc 05 §6.5** | Per-person capacity views vs. small-team suppression. Resolved in §4.14 by role-gating rather than aggregating; doc 05 should reference it |
| **Doc 05 §13** | Already notes the Operations layer has no phase and no effort estimate. Still true, and now larger given §4.13 and mobile capture |
