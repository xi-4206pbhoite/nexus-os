# NEXUS OS — Technical Architecture & Delivery Roadmap

Version 0.9 · 16 August 2026

---

## 1. Architectural shape

NEXUS OS is a multi-tenant SaaS application with four distinct layers. The critical design decision is that **the AI layer never talks directly to source systems** — it only ever receives a prepared, validated data block assembled by the grounding layer. This is what makes "never invent a number" enforceable rather than aspirational.

```
┌───────────────────────────────────────────────────────────────┐
│  PRESENTATION                                                  │
│  Marketing site  ·  11-step onboarding  ·  Dashboard app       │
│  Next.js (React) + Tailwind · SSR for marketing, CSR for app   │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────┴───────────────────────────────────┐
│  APPLICATION / API                                             │
│  Auth & tenancy · RBAC · Billing · Module endpoints            │
│  Background job scheduler · Webhooks                           │
└──────┬──────────────────────────────────────┬─────────────────┘
       │                                      │
┌──────┴───────────────────────┐   ┌──────────┴──────────────────┐
│  GROUNDING LAYER             │   │  DATA & INTEGRATION LAYER    │
│  Company Context assembler   │   │  CRM tables                  │
│  Deterministic calculators   │◄──┤  Website scanner / crawler   │
│  RAG retriever + citations   │   │  Google (GA4, GSC, PageSpeed,│
│  JSON schema validator       │   │    Maps, Custom Search, Ads) │
│  Confidence / exposure math  │   │  DataForSEO                  │
│  Eval harness                │   │  Meta Graph + Ad Library     │
└──────┬───────────────────────┘   │  Accounting (QB/Xero/Zoho)   │
       │                           │  Lead data (Apollo/Clearbit) │
┌──────┴───────────────────────┐   │  Email / WhatsApp senders    │
│  AI LAYER                    │   └──────────────────────────────┘
│  Claude — reasoning core     │
│  GPT — images, voice, cheap  │   ┌──────────────────────────────┐
│      high-volume calls       │   │  STORAGE                     │
│  Structured JSON output      │   │  PostgreSQL (tenant RLS)     │
└──────────────────────────────┘   │  Vector store (embeddings)   │
                                   │  Object storage (documents)  │
                                   │  Cache (generations, API)    │
                                   └──────────────────────────────┘
```

---

## 2. Component responsibilities

| Component | Responsibility | Notes |
|---|---|---|
| **Web application** | Public site, authenticated dashboard, login, permissions, billing screens | Next.js; SSR the marketing site for SEO, dynamic render the dashboard |
| **API / backend** | Module endpoints, orchestration, job dispatch | Python (FastAPI) or .NET — decision open; Python favoured for AI/RAG ecosystem maturity |
| **PostgreSQL** | Companies, users, business profiles, CRM entities, generated content, subscriptions | Row-level security for tenant isolation; Supabase is a reasonable managed default |
| **Vector store** | Embedded chunks of uploaded documents and crawled site content | Each chunk carries tenant ID, source document, page/section — citations depend on this |
| **Object storage** | Uploaded PDFs/DOCX/PPTX/XLSX, generated proposals, ad creatives | Signed URLs only |
| **Company Context assembler** | Builds the Section-0 context block from the Brain on every call | Single code path; no module builds its own context |
| **Deterministic calculators** | Health scores, deltas, confidence percentages, financial exposure, simulation outputs | **Pure code. The AI never produces these numbers.** |
| **RAG retriever** | Chunk retrieval with citation metadata for Proposal Studio and Company Brain Q&A | Hard tenant filter applied before search, not after |
| **Schema validator** | Validates every AI response against its module JSON schema | Retry on failure, then error state — never render unvalidated output |
| **Website scanner** | Crawls the customer's own site during onboarding; reused for competitor sites | Extracts content, SEO signals, contact info, services |
| **Job scheduler** | Nightly data refresh, scheduled scores and briefs, reminders, lead-list refresh | Can start simple (n8n or a hosted scheduler) rather than custom-built |
| **Admin console** | Tenant health, per-tenant AI spend, prompt/model configuration, support tooling | Internal only; separate from customer app |

---

## 3. The grounding layer in detail

This is the part of the architecture that is genuinely novel work and the part most likely to be under-built. Every module request follows the same seven-step pipeline:

1. **Resolve tenant** and load the Company Brain.
2. **Fetch real inputs** — the module declares exactly which data it requires (CRM deltas, GA4 snapshot, DataForSEO response, RAG chunks). Missing inputs are recorded as explicit gaps.
3. **Compute** every number deterministically in code — scores, deltas, percentages, exposure, confidence. Store the calculation trace.
4. **Assemble the prompt** — Company Context Block + module system prompt + the data block containing only fetched and computed values.
5. **Call the model** at the module's mandated temperature (0.2–0.4 for anything factual, 0.6–0.8 only for creative copy).
6. **Validate** the JSON response against the module schema; reject and retry on failure.
7. **Render and audit** — persist the response alongside its input snapshot and calculation trace so any card can answer "why did you tell me this?".

**Model routing.** Claude handles the reasoning core — long-context grounding, strict no-invention discipline, multi-step instruction following. GPT handles what Claude cannot do at all (image generation, realtime voice) and is a candidate for cheap high-volume low-complexity calls where a smaller model saves real money without hurting quality.

**Eval harness.** 22 of the 23 modules in the prompt library carry an explicit "never fabricate" grounding rule (module 20, Company Brain Q&A, is documented as an architecture note rather than a single prompt). Each rule gets automated tests that run in CI on every prompt or model change. A prompt change that breaks a grounding rule fails the build. Without this, prompt drift silently reintroduces hallucination.

---

## 4. Data model (core entities)

```
tenant ──┬── user ── role
         ├── company_profile (the Company Brain: industry, market, services,
         │      ICP, brand voice, preferred/forbidden terms, goals, budget)
         ├── document ── chunk ── embedding
         ├── integration (provider, encrypted tokens, scopes, status)
         ├── competitor
         ├── contact ── company_record
         ├── deal (stage, value, owner, close_date) ── activity
         ├── generation (module, prompt_version, input_snapshot,
         │      output_json, calculation_trace, cost_tokens)
         ├── score_history (department, score, delta, period)
         ├── task
         └── subscription (tier, status, billing events)
```

Two tables carry disproportionate weight. **`generation`** is what makes the product auditable — it is the reason a support ticket about a wrong number can be answered instead of argued about. **`score_history`** is what makes "Improve" real rather than decorative.

---

## 5. Integration inventory

| Integration | Used by | Phase | Notes |
|---|---|---|---|
| Google Analytics 4 (Data API) | KPI dashboard, Morning Brief, Health Score | 1 | OAuth; core data source |
| Google Search Console API | SEO Intelligence, KPI dashboard | 1 | OAuth |
| PageSpeed Insights API | Business Audit | 1 | Free within quota |
| Google Custom Search + Maps Places | Competitor discovery, Lead Intelligence | 1–2 | Free within quota |
| DataForSEO | SEO Intelligence | 1 | Real keyword volume/KD; ~$50/mo |
| Website crawler (own build) | Onboarding scan, competitor content | 1 | Respect robots.txt; rate limit |
| Payment gateway | Billing | 1 | Must support the founder's registered country + international |
| Meta Ad Library API | Competitor War Room | 2 | Free per the cost workbook; confirm Meta's current access requirements — treat as lighter-weight than Graph app review, not zero-friction |
| Meta Graph API | Instagram/Facebook publishing | 2 | Requires app review; start early |
| Accounting (QuickBooks / Xero / Zoho Books) | Finance Advisor, revenue figures | 2 | One provider is enough to start |
| Apollo.io / Clearbit | Lead Intelligence | 2 | ~$100/mo; ZoomInfo deliberately skipped on cost |
| Email sending (SendGrid/Postmark) | Outreach, recovery campaigns | 2 | Free tiers cover early volume |
| WhatsApp Business API (Twilio/360dialog) | "Send WhatsApp" actions | 2 | ~$0.005–0.09 per conversation |
| Google Ads API | Decision Intelligence | 3 | The source groups this with GA4/Search Console as a core KPI-dashboard integration; deferred here because the module that needs it (computed ad-spend recommendations) is Phase 3 |
| OpenAI Images | Ad creative, logo variations | 2–3 | ~$20/mo at moderate volume |
| OpenAI Realtime Voice | Voice CEO (Labs) | 3 | Experimental |

**Compliance constraint, non-negotiable:** lead sourcing is built on web search, Google Search/Maps and public business directories. No scraping of LinkedIn or any platform whose terms prohibit it. If LinkedIn-sourced data is wanted later, the compliant path is the Sales Navigator / official API partner programme.

---

## 6. Delivery roadmap

### Phase 0 — Validation (runs alongside, Weeks 1–4)
Deliver a marketing plan, some content and a proposal manually to 3–5 real clients using the AI APIs directly. Confirms willingness to pay and produces the first realistic prompt tuning data. Cost: near zero. Value: decides whether the rest of the roadmap is worth building.

### Phase 1 — Foundation (Months 1–4)

| Sprint | Focus |
|---|---|
| 1–2 | Environment, architecture finalisation, auth, multi-tenancy, RLS, data model, CI |
| 3–4 | Marketing site + 11-step onboarding wizard + document upload and RAG indexing |
| 5–6 | Website scanner, Business Audit (M2), Company Brain UI, grounding layer + eval harness |
| 7–8 | CRM & pipeline (M5), KPI dashboard (M11) with GA4 + Search Console |
| 9–10 | Growth Planner (M6), Content Studio (M7) |
| 11–12 | Proposal Studio with RAG citations (M8), SEO Intelligence (M9) |
| 13–14 | Morning Brief (M3), Health Score (M4), Nexus Assistant (M10) |
| 15–16 | Billing, admin console, QA hardening, security review, design-partner onboarding |

**Exit criterion:** three design-partner companies complete onboarding unaided and open the Morning Brief in four consecutive weeks.

### Phase 2 — Differentiators (Months 5–8)
Competitor War Room (Meta Ad Library + SEO monitoring + AI interpretation) · Lead Intelligence and prospecting · Customer Intelligence and churn scoring · Finance Advisor with accounting sync · Opportunity Radar including GCC tender feeds · Meta/Instagram publishing (start app review in Month 4) · HR Policies and SOP Builder · Communication Intelligence.

**Exit criterion:** paying customers outside the founder's own network.

### Phase 3 — Moat (Months 9–14)
Business Simulator on a deterministic financial model with AI narration · Decision Intelligence with computed confidence · Company Memory · Voice CEO · Board Packs · Crisis Detector · Arabic-first generation and RTL · workflow automation and email sequencing.

**Exit criterion:** the Simulator and Decision Intelligence are trusted enough that customers cite them as the reason they renewed.

---

## 7. Effort and cost estimate

Indicative, based on the roles named in the source material and the scope above.

| Role | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| Full-stack engineer | 2 FTE × 4 months | 2 FTE × 4 months | 1.5 FTE × 6 months |
| AI / integration engineer | 1 FTE × 4 months | 1 FTE × 4 months | 1 FTE × 6 months |
| UI/UX designer | 0.5 FTE × 4 months | 0.3 FTE × 4 months | 0.3 FTE × 6 months |
| QA / tester | 0.5 FTE × 4 months | 0.5 FTE × 4 months | 0.5 FTE × 6 months |
| Product owner | 0.5 FTE throughout | 0.5 FTE | 0.5 FTE |
| **Total effort** | **~18 person-months** | **~17 person-months** | **~23 person-months** |

Running cost is roughly **$260/month** at validation-stage volume — the low end of the range in the running-costs workbook, rising with usage — lead data and ad intelligence scale fastest. The source material records a setup cost of **INR 49K**; that figure covers initial setup only and is not a build estimate for the scope above.

*These are planning estimates derived from the stated scope, not quoted figures. Blended day rate, team location and how much of Phase 2 gets pulled forward will move them significantly.*

---

## 8. Engineering standards

**Security.** Encryption in transit and at rest. OAuth tokens encrypted with a managed KMS, never logged. Tenant filter applied at the query layer, and separately asserted in RAG retrieval. Audit log for every AI action and every data export. Customer documents are contractually excluded from third-party model training.

**Observability.** Per-tenant token spend and cost dashboards from day one — AI cost is the margin risk and it must be visible before it becomes a problem. Latency tracking per module. Alerting on schema-validation failure rates, which are the leading indicator of prompt or model drift.

**Cost control.** Cache stable generations (a marketing plan does not need regenerating on every page load). Route high-volume, low-complexity calls to cheaper models. Enforce a per-tenant monthly token budget with graceful degradation, not a hard cut-off.

**Testing.** Unit tests on every deterministic calculator — these produce the numbers users trust, so they carry the highest test bar in the codebase. Contract tests on every third-party integration. Grounding evals in CI on every prompt change. End-to-end test of the full onboarding flow.

**Data residency.** Prefer a GCC or EU region and document explicitly where customer data and embeddings live. GCC enterprise buyers will ask this in the first security conversation.

---

## 9. Decisions still open

| Decision | Options | Recommendation |
|---|---|---|
| Backend language | Python (FastAPI) vs .NET | Python — richer AI/RAG ecosystem, faster iteration on the grounding layer |
| Database host | Supabase vs managed Postgres vs Azure SQL | Supabase for speed to MVP; revisit at enterprise scale |
| Keyword data | DataForSEO vs Semrush/Ahrefs API | DataForSEO — Semrush/Ahrefs API access runs $500–1,000+/month and is not justified until much larger |
| AI provider | Claude vs GPT vs both | Both, routed by task — Claude for the grounded reasoning core, GPT for images and voice |
| Payment provider | TBD between three partners | Must support the founder's registered country and international cards |
| Arabic timing | Phase 3 vs Phase 1 | Worth reconsidering — it may be a stronger differentiator than several Phase 2 modules |
