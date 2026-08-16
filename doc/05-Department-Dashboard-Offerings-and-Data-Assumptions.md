# NEXUS OS — Department Dashboard Offerings & Data Assumptions

**What each of the seven AI directors shows, and exactly what information must exist for it to show it**
Version 1.0 · 16 August 2026

---

## 0. Decisions this document is built on

| Decision | Consequence |
|---|---|
| **NEXUS is not the system of record for pipeline.** The customer connects their existing CRM; NEXUS stores only a normalised read-model of it (§9), plus the fallback in §4.12. | NEXUS becomes an intelligence layer over the customer's systems, not a replacement. Removes the biggest blocker for mid-size accounts. Creates a connector build cost and a normalisation requirement. **This reverses the built-in CRM in the business-model document and requires changes to the doc 03 data model — see §13.** |
| **We add an Operations / Delivery layer.** | This becomes NEXUS's **only first-party data source** — the one system of record we own. |
| **The portal presents seven equal AI directors.** | Consistent surface per department, even where service depth genuinely differs. Depth is expressed through data-state, not through a different layout. |

### What the CRM decision changes

The earlier analysis assumed the CRM was NEXUS's data acquisition engine. It no longer is. That role transfers entirely to **Operations / Delivery**, and three new obligations appear:

1. **A CRM normalisation layer is now a required component.** Zoho, HubSpot, Pipedrive, Salesforce, Odoo and Dynamics have different stage models, field names and definitions of "qualified." Every downstream calculation — forecast, health score, stale-deal detection — must run against a canonical model, not against raw provider payloads. Section 9 specifies it.

2. **Connectors are open-ended scope.** One CRM built once becomes N connectors maintained forever. Ship two at MVP, not six.

3. **There is now a hole where a customer has no CRM at all.** We assume a meaningful share of GCC SMEs run sales on WhatsApp and spreadsheets — **an assumption, not a measured figure; validate it with design partners before committing to Deals-lite.** Without our own CRM and without theirs, the Sales Director has no pipeline data — permanently. Section 4.12 proposes the minimum answer: a **Deals-lite** object inside the Operations layer, plus CSV import. This is not a full CRM and should not be marketed as one; it exists so the Sales Director is not empty for the segment least likely to have tooling.

### Two conventions used throughout

**Data states.** Every widget renders in one of four states:

| State | Meaning | Rendered as |
|---|---|---|
| **Live** | All required inputs present and fresh | The real widget |
| **Partial** | Some inputs present; scope is reduced | Widget + explicit scope label ("4 of 6 departments") |
| **Locked** | Required source not connected | The widget's outline + what it needs + a connect action |
| **Warming** | Source connected, insufficient history | "Available from [date] — needs 2 weeks of data" |
| **Self-reported** | Value typed by a user, not fetched from an API | The value + a persistent "entered by you" marker |

**Never a zero, never a blank.** A missing number is a locked state with a named unlock, never `0`, never an empty tile, never an AI estimate.

**Self-reported figures are never silently mixed with API-sourced ones** — in the UI or in the audit trail. This applies to manual budget entry (5.6), Deals-lite (4.12), manual progress and issues (§6), and any imported CSV.

**A global data-completeness meter** sits in the app shell: "You're using 8 of 24 capabilities — 3 connections away from the full executive view." The per-department gap banner in §1 is in addition to it, not a substitute.

---

## 1. Global shell — present on every department page

| Element | What it shows | Assumptions |
|---|---|---|
| **Director header** | Department name, avatar, one-line remit | None |
| **Department score + delta** | Score, week-over-week change, or "Not scored — see why" | Only for the scoreable departments in §10 |
| **Data ribbon** | Which sources feed this department, connection state, last refresh timestamp | Integration registry |
| **Ask this Director** | Chat scoped to this department's data | Company Brain + that department's data block |
| **Action queue** | Recommendations from this director awaiting accept/dismiss | — |
| **Gap banner** | "Connect X to unlock 4 more capabilities here" | Capability-to-source map |
| **Period selector** | 7 / 30 / 90 days, custom | Fiscal calendar from settings |

**Global assumptions required before any dashboard renders:** company profile complete · currency · fiscal year start · timezone · reporting week definition · primary language · user role and department visibility.

---

## 2. Nexus Chief of Staff — Executive

*Consumes every other department. Produces no data of its own.*

| # | Offering | What it shows | Information assumptions |
|---|---|---|---|
| 2.1 | **Morning Brief** | 6 items (revenue, leads, pipeline, traffic, tasks, competitor) + one top recommended action citing ≥2 data points | ≥2 comparable periods in ≥2 departments. **Week 1 shows a Baseline instead.** |
| 2.2 | **Company Health Score** | Composite + per-department breakdown, with visible denominator | ≥1 scoreable department. Composite is labelled against the **six scoreable departments in §10**, e.g. "4 of 6 scored" — never against the seven directors, two of which are synthesis layers and cannot be scored |
| 2.3 | **Today's Priorities** | Ranked cross-department actions | Task objects from Ops + open recommendations |
| 2.4 | **Risk Register** | Top risks with calculated financial exposure | Revenue-by-customer (accounting or CRM), pipeline, delivery milestones |
| 2.5 | **Opportunity Radar** | Tenders, expansion signals, hiring activity | Tenders: a tender data feed — **no provider is identified in any source document; this is an open procurement item (§12)**. Expansion and hiring signals: **Apollo/Clearbit enrichment only** (Phase 2), not derivable from a tender feed. Plus ICP, industry, geography |
| 2.6 | **Decision Queue** *(Phase 3)* | Decisions needing approval, with computed confidence | **Ad platform timeseries only** — Google Ads API, Phase 3. Pipeline data cannot substitute; the prompt module is entirely ad-spend shaped. **Confidence computed in code**, never by the model |
| 2.7 | **Department Briefings** | One status line per department, linking through | Each department's own state |
| 2.8 | **Company Brain status** | Facts known, sources, unconfirmed assumptions | Onboarding + crawl + documents |
| 2.9 | **Board Pack export** *(Phase 3)* | Assembled PDF/PPTX for board or bank | ≥1 quarter of history |

**Structural note.** This director cannot be better than the departments beneath it. With nothing connected it shows only 2.8 plus the audit — and it must say so plainly rather than filling space.

---

## 3. AI Marketing Director

*The earliest department to become useful — but see the corrected degraded-reality note at the end of this section.*

| # | Offering | What it shows | Information assumptions |
|---|---|---|---|
| 3.1 | **Marketing score + drivers** | Score, delta, what moved it | **GA4 is required — Marketing is not scoreable without it.** Crawl and DataForSEO support separate *Brand* and *SEO* audit scores, which must not be merged into a Marketing score to manufacture a number |
| 3.2 | **Traffic & conversion trend** | Sessions, users, sources, on-site conversion rate | **GA4 OAuth.** On-site conversion additionally needs goals/events configured in GA4 — verify at connect, warn if absent. **Lead-to-customer conversion is a different metric and needs CRM as well** — keep the two visually distinct |
| 3.3 | **Channel performance** | Traffic by channel; cost by channel where available | GA4 for traffic. **Cost columns have no connector at MVP** — the only ad-spend integration in the inventory is Google Ads (Phase 3), and there is no Meta Marketing API. Ship traffic-only, with cost as self-reported or locked |
| 3.4 | **Growth Plan (90-day)** | Audience, positioning, channel mix, budget split, timeline | Company Brain + stated monthly budget + goals. Pure generation — **works with nothing connected** |
| 3.5 | **Content & Campaign Calendar** | Scheduled and drafted items | Internal objects only |
| 3.6 | **Content Studio** | Blog, ad copy, email, captions, video scripts | Brand voice + preferred/forbidden terms. Pure generation |
| 3.7 | **SEO Intelligence** | Keyword table (volume, difficulty), gaps, briefs, technical issues | **DataForSEO for volumes — never estimated.** Rankings need Search Console. Technical issues from crawl + PageSpeed |
| 3.8 | **Brand Intelligence** | Voice consistency, positioning statement, messaging gaps | Crawl + brand guideline documents |
| 3.9 | **Competitor War Room** *(Phase 2)* | Competitor ads, new pages, ranking moves, alerts, interpretation | Competitor list + SEO competitor tracking + ad data. **Ad data is either a paid aggregator (~$35/mo, the cost workbook's default) or direct Meta Ad Library access — the latter is free but its current access requirements are unconfirmed. Not zero-friction, and not day one** |
| 3.10 | **Social publishing** | Queue, schedule, publish | Meta Graph OAuth + app review |
| 3.11 | **Ad creative generation** *(Phase 2)* | Generated image variants | Brand assets (logo, palette) + the messaging angle |
| 3.12 | **Landing page / CTA recommendations** | Prioritised on-page fixes | Crawl + GA4 page-level behaviour |

**Degraded reality, stated precisely.** With only a website URL: 3.8 works, and the market half of 3.7 (volumes and difficulty, not rankings) works.

Once the Stage-3 onboarding questions are answered — goals, budget, brand voice, forbidden terms, competitor list — 3.4, 3.5, 3.6, 3.11 and the on-page half of 3.12 also work. **These are not URL-only**: the Growth Plan's budget allocation must sum to a stated budget, and Content Studio depends on prohibitions that cannot be inferred from a website.

3.9 is Phase 2. 3.1, 3.2, 3.3 and the ranking half of 3.7 need GA4 or Search Console.

That is still a real product on day one — but it is a *questionnaire-plus-crawl* product, not a *URL-only* product, and the flow in doc 04 should be read with that correction.

---

## 4. AI Sales Director

*Reads the customer's CRM. Owns no pipeline data.*

| # | Offering | What it shows | Information assumptions |
|---|---|---|---|
| 4.1 | **Sales score + drivers** | Score, delta, cause | Normalised pipeline (§9) |
| 4.2 | **Pipeline overview** | Value by stage, count, movement, kanban or list | Connected CRM with: stage, value, close date, owner, last-activity timestamp. **Any missing field disables the dependent widget, not the whole page** |
| 4.3 | **Forecast** | Weighted and committed forecast for the period | ≥3 months of closed history for win rates. Below that: unweighted totals only, labelled |
| 4.4 | **Stale / at-risk deals** | Deals with no activity beyond a threshold | Reliable activity timestamps — **the field most often empty in real CRMs.** Verify at connect; if absent, disable rather than guess |
| 4.5 | **Lead Intelligence** *(Phase 2)* | Discovered prospects, match score, why-this-lead, decision-maker, suggested opener | ICP + industry + geography. Apollo/Clearbit for enrichment. **Works with no CRM connected** |
| 4.6 | **Push to CRM** | Write discovered leads into their CRM | **Write scope** on the connector — a much heavier permission than read. Ask separately, later |
| 4.7 | **Proposal Studio** | Client-ready proposal, every price cited to a source document | Uploaded price list / service catalogue, RAG-indexed. **Works with no CRM connected** |
| 4.8 | **Outreach drafting** | Email / WhatsApp / message drafts in brand voice | Contact context + brand voice |
| 4.9 | **Communication Intelligence** | Suggested communication style per contact | Optional Crystal integration — **not currently in the doc 03 integration inventory (§13)**. The prompt module requires "suggested" / "based on available profile" phrasing, never "this person is." The additional prohibition on use in hiring decisions is **our policy, not an inherited constraint** |
| 4.10 | **Win/loss analysis** | Patterns in won vs lost deals | ≥20–30 closed deals with loss reasons populated |
| 4.11 | **Customer health & churn** *(Phase 2)* | Health score, churn risk, revenue at risk, recovery plays | CRM activity history + payment behaviour (accounting) + review sentiment. Needs ≥6 months |
| 4.12 | **Deals-lite** *(fallback)* | Minimal deal tracker inside the Ops layer for customers with no CRM | Manual entry or CSV import. **Explicitly not a CRM** |

**Degraded reality:** no CRM connected → 4.5, 4.7, 4.8 still work. That's a coherent "prospecting and proposals" product. Everything else locks with a named unlock.

---

## 5. AI Finance Advisor

*Entirely gated on one connection.*

| # | Offering | What it shows | Information assumptions |
|---|---|---|---|
| 5.1 | **Finance score + drivers** | Score, delta | Accounting connection |
| 5.2 | **Revenue trend** | By month, by service, by customer | Accounting API, or CRM closed-won as a weaker proxy (label the source) |
| 5.3 | **Margin analysis** | Gross and net margin, by service or project | Revenue + cost. **Project-level margin requires cost data from the Ops layer** |
| 5.4 | **Cash position & runway** | Balance, burn, runway | Accounting, ≥3 months |
| 5.5 | **Receivables ageing** | Overdue invoices, collection risk, chase drafts | Accounting invoice data with due dates |
| 5.6 | **Expenses vs budget** | Category spend against plan | Accounting + a budget entered by the user (no source supplies this) |
| 5.7 | **Pricing recommendations** | Where prices are below market or margin | Price list + margin data + competitor pricing where public |
| 5.8 | **Budget scenarios** | Compare planned allocations | 5.6 |
| 5.9 | **Business Simulator** *(Phase 3)* | Price change, hiring, expansion — modelled | Current revenue, margin and customer data are required. Historical pricing/demand data is **optional** — where absent, the prompt module requires the output to state explicitly that it is a general industry-pattern approximation, not derived from this company's own data. That is the one sanctioned exception to §0's "never an estimate" rule, and it must carry the label. Cost structure and headcount cost needed for hiring scenarios. **Deterministic model in code; AI narrates only** |
| 5.10 | **"Can I afford X?"** | Q&A grounded in real financials | 5.4 + 5.9 |

**Two setup steps that are easy to under-scope:** a **chart-of-accounts mapping** (their account names → NEXUS canonical categories) is required before any of this is trustworthy, and a **budget entry screen**, because no API supplies a budget.

---

## 6. AI Operations Director — the first-party layer

*The only system of record NEXUS owns. Its adoption now determines whether the executive layer ever works.*

### 6a. Entities NEXUS will store

```
project ── milestone ── task ── assignee
   ├── client_ref        (links to connected CRM contact/account)
   ├── contract_value    (or links to CRM deal)
   ├── dates             (start, planned end, actual end)
   ├── progress          (manual % or derived from milestones)
   ├── cost_line         (labour, materials, subcontract)
   ├── subcontractor / vendor
   ├── issue / snag      (severity, owner, status)
   └── document          (drawings, permits, reports — RAG-indexed)
```

### 6b. Offerings

| # | Offering | What it shows | Information assumptions |
|---|---|---|---|
| 6.1 | **Operations score + drivers** | Score, delta | Active projects with dates and progress |
| 6.2 | **Active projects board** | Status, % complete, on-time / late / at-risk | Project + milestone dates + progress updated within the period |
| 6.3 | **Milestone timeline** | Gantt-lite across projects | Milestones with planned dates |
| 6.4 | **Task queue & overdue** | Assigned work, overdue items | Tasks with assignee and due date |
| 6.5 | **Capacity & utilisation** | Who is on what, over/under-loaded | Team roster + task assignment + working-hours assumption |
| 6.6 | **Bottleneck analysis** | Where work consistently stalls | ≥1 month of stage-transition timestamps |
| 6.7 | **Project profitability** | Cost vs contract value per project | Cost lines from Ops + revenue from Finance — **the key cross-department interlock** |
| 6.8 | **Delivery risk alerts** | Late milestones and the revenue they threaten | 6.2 + 6.7 |
| 6.9 | **Issue / snag register** | Open issues by severity and owner | Manual entry |
| 6.10 | **Subcontractor performance** | On-time rate, issue rate per vendor | ≥3 completed engagements per vendor |
| 6.11 | **SOP library + builder** | Generated and stored SOPs | Pure generation |
| 6.12 | **Project document vault** | Per-project files, RAG-searchable | Uploads |

### 6c. The adoption problem, stated plainly

The Operations layer only produces data if people update it — and site teams are not at desks. This is the same adoption dependency the CRM had, moved to a harder population. Three consequences for the plan:

- **Mobile-first capture is not optional** for progress, issues and photos.
- **Progress should be derivable from milestone completion**, so the common case is ticking a box rather than typing a percentage.
- **Ops adoption becomes the single most important activation metric in the product** — above logins, above onboarding completion.

---

## 7. AI HR Director

*Mostly generative — but the Ops layer gives it one real data source.*

| # | Offering | What it shows | Information assumptions |
|---|---|---|---|
| 7.1 | **Team directory & org view** | People, roles, reporting lines | Roster from onboarding |
| 7.2 | **Capacity & utilisation** | Load per person | Assigned hours from Ops task assignment — **measured**. Available hours come from a working-hours assumption in settings — **not measured**. The ratio is therefore part-assumption and must be labelled |
| 7.3 | **Policy library & generator** | HR policies in company voice | Pure generation + jurisdiction |
| 7.4 | **JD generator & hiring plan** | Role descriptions, hiring sequence | Roster + growth plan + budget |
| 7.5 | **Onboarding checklists** | Per-role checklist, assignable as Ops tasks | Roster + SOPs |
| 7.6 | **Training plans** | Skill gaps and outlines | Roster + roles. Skill gaps are self-declared, not measured — **label as such** |
| 7.7 | **Leave & attendance** | *Out of MVP* | Would need an HRIS integration that does not exist in the inventory |

**Jurisdiction warning:** GCC labour law is country-specific. Generated policies must carry a review-by-local-counsel disclaimer and be templated per country, not generated free-form.

---

## 8. AI Strategy Director

*A synthesis director, like the Chief of Staff.*

| # | Offering | What it shows | Information assumptions |
|---|---|---|---|
| 8.1 | **Market position** | Where the company sits vs competitors | Competitor data + crawl + SEO share |
| 8.2 | **Service portfolio analysis** | Which services to grow, fix or drop | Revenue by service (Finance) + margin (Finance + Ops) + demand (DataForSEO) |
| 8.3 | **Expansion analysis** | New market or service entry case | 8.1 + 8.2 + market data for the target geography |
| 8.4 | **Scenario planning** | Compare strategic options | Shares the Simulator engine with Finance |
| 8.5 | **Bid / no-bid advisor** | Recommend whether to chase a tender, and at what price | Tender detail + win/loss history + current capacity (Ops) + margin floor (Finance). **High value for contracting; needs three departments live** |
| 8.6 | **Risk register** | Shared with Chief of Staff | §2.4 |

**Overlap flag:** Strategy and Chief of Staff share a lot of surface. Keeping both as separate directors is a presentation choice, not an architectural one — they should read from the same computed objects so they can never disagree with each other.

---

## 9. Required new component — CRM normalisation

Because pipeline data is now external, every downstream calculation runs against a canonical model.

**Canonical deal object:** `external_id · account · contact · value · currency · stage_canonical · stage_native · probability · created_at · expected_close · last_activity_at · owner · source · status (open/won/lost) · loss_reason`

**Canonical stages:** `New → Qualified → Proposal → Negotiation → Won / Lost`. Every provider's stages map into these; the native label is retained for display.

**At connect time, run a field-completeness check** and show the customer exactly what NEXUS can and cannot calculate from their CRM. A CRM with no `last_activity_at` cannot support stale-deal detection — say so at connect, not later via an empty widget.

**MVP connector scope:** two providers only, plus CSV import, plus Deals-lite. Add providers on customer demand. **Which two is an open question** — Zoho and HubSpot are the working assumption on expected GCC SME prevalence, but no source document contains CRM market-share data for the region. Confirm with the first design partners rather than building on the guess.

---

## 10. Which departments are scoreable

A department is scoreable only where measurable state exists.

**Scoreable departments are not the same set as the seven directors.** Six departments can carry a score; Customers is one of them but has no director page of its own — it lives inside the Sales Director (4.11). Chief of Staff and Strategy are synthesis layers and are never scored.

| Scoreable department | Scoreable | Basis | Caveat |
|---|---|---|---|
| Marketing | Yes | GA4 (required) + Search Console + DataForSEO | Not scoreable on crawl alone |
| Sales | Yes | Normalised CRM pipeline | Requires a connected CRM with populated stage, value and close-date fields |
| Finance | Yes | Accounting API | Single point of failure |
| Customers | Yes | Reviews + CRM activity + payment behaviour | Surfaced under the Sales Director |
| Operations | **Yes — conditional** | First-party project, milestone and task data | **Conditional on adoption, not on an API.** Unlike Finance, this score fails if people stop updating it — see §6c |
| HR / People | **Partial** | Utilisation only, and the denominator is an assumption (§7.2) | Do not present as a full department score. Note it derives from Ops, so Ops adoption failure takes both down together |
| Chief of Staff · Strategy | No | Synthesis layers | — |

**The composite must always display its denominator** — "72 / 100 across 4 of 6 scored departments" — and list what the unscored ones need. The maximum is 6, never 7.

---

## 11. Cross-department interlocks worth designing deliberately

These are where the product stops being a bundle and starts behaving like one system. Each is cheap once both sides exist, and each is a strong demo.

| Interlock | Combines | Produces |
|---|---|---|
| Project profitability | Ops cost + Finance revenue | True margin per project |
| Delivery risk → revenue risk | Ops milestones + CRM deal value | "This slip threatens OMR X" |
| Capacity → bid decision | Ops utilisation + tender pipeline | "You can't deliver this if you win it" |
| Win/loss → content | CRM loss reasons + Content Studio | Content aimed at real objections |
| Churn → retention campaign | Customer health + Marketing | Targeted recovery campaign |
| Cash → marketing budget | Finance runway + Growth Plan | Budget advice grounded in actual cash |

---

## 12. Open items created by this draft

1. **Deals-lite scope** — how minimal can it be and still make the Sales Director useful for a no-CRM customer?
2. **Ops mobile capture** — web-responsive at MVP, or a real mobile experience?
3. **Cost data entry burden** — project profitability needs labour rates and material costs. Who enters them, and how often?
4. **CRM write scope** — offer at MVP, or read-only until trust is established?
5. **Chart-of-accounts mapping** — automated suggestion with user confirmation, or fully manual?
6. **Per-country HR policy templates** — which jurisdictions at launch?

---

## 13. Changes this document forces elsewhere

This spec is not consistent with the earlier documents. Three things must be updated before build.

| Document | What changes |
|---|---|
| **Doc 03 §4 (data model)** | Remove first-party `contact` / `company_record` / `deal` / `activity` as owned entities; replace with the normalised CRM read-model (§9). Add the Operations entities from §6a — `project`, `milestone`, `cost_line`, `issue`, `subcontractor`, per-project `document` — none of which exist there today. |
| **Doc 03 §5 (integration inventory)** | Add rows that are used by this spec but missing from the inventory: **Google Business Profile / reviews** (required by prompt modules 1 and 12), **Crystal** (module 17), **tender data feed** (no provider identified), and the **two CRM connectors**. Each also needs a cost line, which the running-costs workbook does not currently have. |
| **Doc 03 §6–§7 (roadmap and effort)** | The Operations layer and mobile capture (§6c) carry no phase and no effort estimate. Both must be added, and the ~18 person-month Phase 1 figure revisited. |
| **Business-model document** | Its Phase-1 scope specifies a built-in CRM. That is now reversed. |
| **Doc 04 (flow analysis)** | Its "website only" column is slightly optimistic for Marketing: the Growth Plan and Content Studio need Stage-3 answers, not just a URL. See the corrected note in §3. |

**One coverage gap worth naming.** Roughly half the offerings in this document — the forecast, win/loss, pricing, budget scenarios, all twelve Operations widgets, and most of HR and Strategy — have no corresponding module in the supplied prompt library. Doc 03's eval harness is scoped precisely to that library's 23 modules. Every new offering needs its own grounding rule and its own eval, or the CI safety net covers only half the surface it appears to cover.

---

## 14. Provenance of the figures in this document

Two kinds of claim appear in the "Information assumptions" column, and they should not be read the same way.

**Sourced.** Anything naming a provider, a prompt module's required inputs, a grounding rule, or a phase — these trace to the business-model document, the prompt library, the cost workbook or doc 03.

**Engineering judgement — not sourced, and open to challenge:** `≥3 months of closed history` for a weighted forecast · `≥20–30 closed deals` for win/loss patterns · `≥12 months` for full simulator confidence · `≥1 month of stage-transition timestamps` for bottleneck analysis · `≥3 completed engagements` for subcontractor scoring · `≥1 quarter` for a board pack · `≥2 comparable periods in ≥2 departments` for the Morning Brief. Only the `~6 months` for customer LTV has partial support in the earlier analysis.

These thresholds decide when a widget flips from Warming to Live, so they are worth setting deliberately with the first design partners rather than inheriting them from this draft.
