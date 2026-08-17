# NEXUS OS — Decisions Required Before / During Build

Per doc 07 §1: *"If the spec is ambiguous or two documents disagree, stop and ask. Do not invent a resolution and proceed."*

I have invented no resolutions. Conflicts that doc 07's own precedence rule settles are listed in `ARCHITECTURE.md` §0 and need no answer from you — only the items below do.

**Only §1 and §2 block M0.** Everything in §3 blocks a later milestone and can be answered when we reach it.

---

## 1. Environment blockers — M0 cannot complete without these

These are not spec questions; they are missing prerequisites on this machine. M0's done-when is *"`docker compose up` gives a running web and API"*, which is currently impossible.

### ~~E1 — Docker is not installed~~ · RESOLVED (ADR 0001, then ADR 0006/0007)

Settled: Docker Engine in WSL2 serves pgvector; Docker Desktop is ruled out. Original text kept below.
`docker` is not on PATH and Docker Desktop is not present at the default location. Doc 07 §3 requires Postgres + pgvector + object storage via Compose, and M0's acceptance is a working `docker compose up`.

**Options:** (a) install Docker Desktop — matches the spec exactly; (b) run Postgres+pgvector natively on Windows and drop Compose — diverges from doc 07 §3 and M0's acceptance criterion.
**My recommendation:** (a).

### E2 — Python is 3.10.11; doc 07 §3 requires 3.12
Only `3.10-64` is registered. Several things I would otherwise use freely (PEP 695 generics, `TypeVar` defaults, the 3.12 `asyncio` improvements) are unavailable, and more importantly the spec names 3.12.

**Options:** (a) install Python 3.12 locally; (b) develop entirely inside the Docker image, which pins 3.12 regardless of the host — this makes E2 moot if E1 is resolved.
**My recommendation:** (b), with (a) as a convenience for editor tooling.

### E3 — `D:\Projects\NEXUS_OS` is not a git repository
Doc 07 §5.5 requires small commits with clear messages. There is no repo, so there is no commit history to make.

**Ask:** confirm I should `git init` at `D:\Projects\NEXUS_OS` and make the first commit contain `/doc` plus these three planning artifacts. Also confirm whether a remote exists that I should push to, or local-only for now.

---

## 2. Decision blocking M0

### D1 — Embedding model provider
No source document names one. This is needed in M0 because the `embedding` column's dimension is fixed in the first migration that creates it, and changing it later means a re-embed of every chunk.

| Option | Dimensions | Notes |
|---|---|---|
| **Voyage** (`voyage-3`) | 1024 | Anthropic's recommended pairing; strong retrieval quality; adds a second vendor |
| **OpenAI** (`text-embedding-3-large`) | 3072 (truncatable) | Reintroduces OpenAI, which doc 06 §12 flags as an open question (see D11) |
| **Local** (`bge-m3` / `e5`) | 1024 | No per-token cost, no data leaving infrastructure — relevant to the doc 01 §6 residency commitment; needs GPU or tolerable CPU latency |

**My recommendation:** Voyage `voyage-3` at 1024 dimensions. Best quality-per-cost for RAG, and it keeps the retrieval path on one vendor family. I will store the model id and dimension on every chunk row so a future migration is possible without guesswork.

---

## 3. Decisions blocking later milestones

### D2 — DataForSEO account *(blocks M7)*
Doc 05 §3.7 requires real keyword volumes and forbids estimating them; doc 06 §1.2 requires it be post-verification only. ~$50/month per doc 03. **Do you have credentials, or should keyword data render Locked until you do?**

### D3 — Google API credentials *(blocks M2 partially, M10 fully)*
PageSpeed Insights (M2), plus GA4 and Search Console OAuth (M10) need a Google Cloud project with a client id/secret and an authorised redirect URI. PageSpeed works keyless at low volume but is rate-limited — acceptable for M2 dev, not for M10.

### D4 — Production email provider *(blocks M3)*
M3 needs verification email. Dev uses mailpit in Compose, so this only blocks a real deployment. Doc 03 names SendGrid/Postmark as Phase 2. **Which, and do you have an account?**

### ~~D5 — Contributor L3 subset~~ · RESOLVED (ADR 0005)

Ratified as proposed and shipped in M4. `decide_l3_access` implements it and `test_contributor_scope.py` proves it. Doc 06 §11.5 asks for a per-department definition with a design partner, so this is the default to revisit, not the final word. **Original text kept below for that revisit.**

Doc 06 §2.3 says a Contributor gets *"own department, restricted subset — excludes department-wide financial aggregates and other people's records."* That is a principle, not a specification, and M4's acceptance is *"a Contributor cannot reach L3 aggregates"* — which I cannot test without the per-department definition.

**My proposed default, for you to ratify or correct:** a Contributor sees (i) records where they are the owner or assignee, (ii) records they created, (iii) department reference data (stages, services, price list); and is denied (iv) any aggregate over the department, (v) any record owned by another user, (vi) any field marked `sensitivity: financial` on a record they do not own. Doc 06 §11.5 says define it per department with a design partner — so I would ship this default and revisit.

### D6 — A Department Manager sees six directors, not seven *(blocks M4)*
Doc 06 §2.4 restricts the Executive surface to Owner and Executive at MVP, which removes the Chief of Staff page, the Morning Brief and the composite score for everyone else. Doc 05 §1 promises "seven equal AI directors" with a consistent surface. Doc 06 records this as an unresolved contradiction and recommends the restriction anyway.

**Confirm:** ship the six-director experience for Department Managers, Contributors and Viewers? This is product-visible, so I do not want to assume it.

### D7 — Which departments are actually in MVP? *(shapes M9–M12)*
Doc 07's milestones build **Marketing** (M9) and **Operations** (M11). Chief of Staff, Sales, Finance, HR and Strategy have no milestone. Combined with doc 07 §8's exclusions, that leaves MVP as: audit + Company Brain + Marketing + Operations + assistant.

Two consequences worth your explicit sign-off:

1. **Finance ships as a fully Locked page.** Accounting is out of scope and doc 05 §5 says Finance is *entirely* gated on that one connection — so it is seven "connect accounting" tiles and no working surface.
2. **Sales is nearly empty too.** Lead Intelligence (4.5) and Customer health (4.11) are Phase 2 and therefore excluded; Proposal Studio (4.7) has no milestone. With a CRM connected, M10 gives pipeline data but no Sales director page exists to render it.

**Is that the intended MVP, or should Sales + Proposal Studio be added as a milestone?**

### D8 — Capability count: 21 or 24? *(blocks M9)*
Doc 04 §6 specifies the completeness meter as *"6 of 21 capabilities"*; doc 05 §0 says *"8 of 24"*. Doc 06 §12 records this as needing reconciliation. The meter is in the global shell, so M9 needs the canonical number.

**My recommendation:** build a capability registry as data — each capability declaring its required sources — and derive the denominator from it. Then the number is computed rather than asserted, and it self-corrects as scope changes. I would still want you to ratify the registry contents at M9.

### D9 — Preview data TTL *(needs ratification, not a decision from scratch)*
Doc 06 §1.1 and §10 say "short TTL" without a value. This governs crawl data held for a domain whose owner has no account and has not consented.

**The code has moved ahead of this entry.** `preview_ttl_hours` is now **24 hours**, changed alongside the preview cache with the reasoning that the subject is a company that never consented to the crawl, and a day is long enough to serve a reload. That supersedes the 7 days originally recommended here.

**What is still needed from you:** ratify 24 hours, or name a different number. And the deletion-request path doc 06 §10 requires **does not exist** — there is no way for a domain owner to ask for their audit to be removed before it expires. That is the part of D9 still genuinely open.

### D10 — Which CRM connector? *(blocks M10)*
Doc 05 §9 names Zoho and HubSpot as a *working assumption on expected GCC SME prevalence*, explicitly flags that no source contains regional market-share data, and says confirm with design partners rather than building on the guess. Doc 07 M10 narrows it to **one** connector and doc 07 §8 puts a second out of scope.
**Which one?** This also determines whether `last_activity_at` is reliably populated, which decides whether stale-deal detection exists at all.

### D11 — Is any non-Claude model needed? *(blocks M12)*
Doc 03 §9 routes images and voice to GPT. Doc 07 §8 puts Voice out of scope; ad-creative generation is doc 05 Phase 2 and therefore also out. So MVP appears to need **no OpenAI dependency at all** — unless D1 selects OpenAI embeddings.
**My recommendation:** Claude-only for MVP. Confirm.

### D12 — Deals-lite: in or out? *(blocks M10/M11 scope)*
Doc 05 §4.12 proposes a minimal deal tracker inside the Ops layer so the Sales Director is not permanently empty for customers with no CRM — and doc 05 §0 flags the underlying premise (that many GCC SMEs run sales on WhatsApp and spreadsheets) as *an assumption, not a measured figure.* Doc 07 neither includes it in a milestone nor excludes it in §8.
**My reading:** out of MVP, since no milestone carries it. Confirm — if it is in, it belongs in M11 alongside the Ops entities.

### D13 — Anthropic API access *(blocks M12)*
The Agent SDK needs an API key and a decision on which model tier backs each execution mode. Also relevant to doc 06 §8.4's cheap-model routing, which is only permitted where that module's evals pass.

### D14 — Login rate limiting *(blocks exposing the sign-in UI publicly)*

**Raised by ADR 0009.** `POST /auth/login` accepts unlimited attempts. `rate_limit.py` covers only the Preview path, so nothing bounds password guessing. argon2id and the dummy-hash timing equalisation defeat offline cracking and the timing oracle; **online guessing against a weak password is unmitigated.**

Now urgent because a sign-in form exists, where before this required deliberate API calls.

Three questions, and the third is why this is not a default I can pick:

1. **Key by IP, by email, or both?** Per-IP alone is defeated by a botnet; per-email alone is defeated by rotating targets.
2. **What is the response** — 429 with `Retry-After` (consistent with Preview), or a silent delay? A 429 keyed by email confirms the address exists, which would undo M1's account-enumeration work.
3. **Lock the account after N failures?** A per-account lock is a **denial-of-service vector against a named user**: anyone who knows an Owner's email can lock them out at will. The usual answer is exponential backoff rather than a lock, but "the Owner cannot get in during an incident" is a business call, not a technical one.

My recommendation if you want one: per-IP *and* per-email counters, exponential backoff instead of a lock, and an identical 401 in every case with the delay applied silently — so nothing observable distinguishes a rate-limited known address from an unknown one. That preserves the enumeration guarantee, which is the property most easily lost here.

### D15 — Department-branched onboarding for invited members *(new scope; would extend M4)*

**Raised by you**, and it is not in any source document — which is why it is here rather than being built.

Onboarding today is a **company setup flow, run once by the founder**. Doc 04 §5 redesigns it as six stages — audit, justified questions, connections, documents, team last — and there is no "select your department" step, because the person running it is configuring the whole company.

`Question.department` exists on the catalogue but means something different from what the name suggests: it records **which department owns the answer as an L3 fact**, so `average_deal_size` is L3 Sales and `monthly_marketing_budget` is L3 Finance. Doc 06 §2.5 is explicit — *"Tag them at capture"* — it is a scope classification, not a routing rule. Only 2 of the 14 questions carry one; the other 12 are company-wide.

**What you appear to want is a second flow**: when a Sales Manager accepts an invitation, ask them Sales-specific questions. That is reasonable and no document rules it out. It is also genuinely new work, and it raises three questions worth deciding before it is built:

1. **Does a member's answer bind the department, or only themselves?** If an invited Sales Manager states the average deal size, that becomes an L3 Sales fact the whole department reads. Two managers can disagree. The Brain's conflict precedence (M7 task 7.4) puts user-confirmed above crawl, but not one user above another.
2. **Who may answer department-scoped questions?** A Contributor is denied department aggregates by ADR 0005. Letting one *write* a department-wide fact through an onboarding form would route around that boundary.
3. **What happens when someone changes department?** Their answers stay tagged to the old one unless something re-classifies them, which is the same problem M5 task 5.10 solves for superseded documents.

**My recommendation:** build the founder flow first (task 4.10) and treat member onboarding as a follow-on. Restrict department-scoped questions to the Owner, Executive and that department's Manager, and have Contributors confirm rather than assert. But this is your product call, and answering (1) is what unblocks the design.

---

## 4. Assumptions I have made — object if any is wrong

| # | Assumption | Basis |
|---|---|---|
| A1 | Repo root is `D:\Projects\NEXUS_OS`; the landing page moves `nexus_os_application/web` → `apps/web` | `/doc` is at that root and doc 07 §4 shows `/apps/web` as a sibling |
| A2 | MFA / SSO / SCIM are out of MVP | Doc 06 §10 flags them absent from every document; doc 07 neither includes nor excludes them |
| A3 | Trial is a flag set at workspace creation; no paywall | Doc 07 §8 — "billing beyond a trial flag" is out of scope |
| A4 | k-anonymity threshold = 3, configurable | Doc 06 §4.14 — "3 is conventional; confirm against real team sizes" |
| A5 | CRM connector is read-only at MVP | Doc 05 §4.6 — write scope is "much heavier, ask separately, later" |
| A6 | Opportunity Radar / tender feed is out of MVP | Doc 05 §2.5 — no provider identified in any source document; no milestone covers it |
| A7 | No OCR — scanned PDFs fail visibly | Doc 07 M5 requires the failure be visible, not silent; no OCR dependency is named anywhere |

---

## 5. What I need from you to start M0

1. **E1 / E2** — install Docker Desktop (recommended), or tell me to drop Compose
2. **E3** — confirm `git init` at the repo root, and whether there is a remote
3. **D1** — embedding provider (recommendation: Voyage `voyage-3`, 1024d)
4. Approval of `ARCHITECTURE.md` and `TASKS.md`

Everything else can wait for the milestone that needs it.
