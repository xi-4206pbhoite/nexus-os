# NEXUS OS — Flow & Cold-Start Analysis

**What we ask the user, and what we can honestly show when they give us nothing**
Version 0.9 · 16 August 2026

> This document is deliberately adversarial toward the solution. The other documents in this set describe what NEXUS OS should be. This one tests whether the flow actually holds up, and it concludes that the current onboarding-to-dashboard flow has a structural problem that has to be fixed before build, not after.

---

## 1. The finding, up front

The prototype's dashboard leads with **1,247 leads · OMR 32,940 revenue · 8,653 visitors · 312% ROI · Health 82/100 · "revenue up 12.7% this week."**

Not one of those numbers is available to any customer on day one. Several are unavailable *permanently* to a customer who connects nothing and doesn't work inside the NEXUS CRM.

That is not a bug in the demo — demos need numbers. It is a bug in the flow, because the flow is designed as though the data will be there. It won't be, and the product's own core rule ("never invent a number") forbids the obvious shortcut.

**The sharpest version of the problem:** the capabilities that work with zero customer data are the marketing and competitive ones — which look most like the point tools NEXUS is differentiating from. The capabilities that justify the name "executive operating system" are exactly the ones that need the most customer data. The product is currently sequenced so that the weakest-differentiated half arrives first and the strongest half may never arrive at all.

---

## 2. What the flow asks today

The prototype's 11 steps, and what each actually collects:

| # | Step | What it collects | Type |
|---|---|---|---|
| 1 | Welcome | — | Screen |
| 2 | Company Basics | Name, website, email, phone, country, industry, employee count, annual revenue (optional), business description, logo | 10 fields |
| 3 | Website Scan | Automated crawl → services, segments, keywords, competitors, tone, market | Automated |
| 4 | Business Goals | Multi-select from 8 + other | 1 field |
| 5 | Customers & Revenue | Salespeople, branches, ideal customer, average deal size, monthly marketing budget, biggest challenges | 6 fields |
| 6 | Brand Voice | Pick from 7 + custom | 1 field |
| 7 | Products & Services | Main products/services, price range, delivery area, differentiator | 4 fields |
| 8 | Competitors | Manual entry (up to 4) or auto-discovery | 0–4 fields |
| 9 | Upload Knowledge | Documents (PDF/DOCX/PPTX/XLSX, 50 MB each) | Uploads |
| 10 | Connect Tools | Website/social, Google, marketing, CRM, accounting | 5 OAuth groups |
| 11 | Team & Permissions | Invite members, assign roles | Variable |

Roughly **25–30 typed fields, a document upload step, and five OAuth groups**, against a stated "about 7 minutes."

### The problems with it

**a) It front-loads all the cost and back-loads all the value.** The user does seven minutes of work before seeing a single thing about their own business. The audit — the one moment that proves the product knows something — sits behind the entire questionnaire. It should be the first thing, not the last.

**b) It asks humans to type what the crawler already extracted.** Step 3 scans the website and reports "7 services, 3 customer segments, 12 keywords, 4 competitors, professional and technical tone, Oman as primary market." Then steps 6, 7 and 8 ask the user for tone, services and competitors. Confirming an extracted answer takes seconds; typing it cold takes minutes and produces worse data.

**c) The OAuth step is placed at maximum distrust and asks for the most.** Step 10 requests analytics, CRM *and accounting* access from someone who has used the product for four minutes and has not yet seen it do anything. Accounting access is the highest-friction permission in the entire inventory and it is bundled with the rest as though it were equivalent to connecting Instagram.

**d) "Skip for now" is offered but nothing tracks the consequence.** Every connection group can be skipped, which is correct — but the flow never tells the user what skipping costs, and the dashboard afterwards doesn't show what's missing. The user skips five groups, lands on a dashboard, and either sees empty tiles with no explanation or (worse) plausible-looking numbers.

**e) Several questions are collected and never used.** Phone number and branch count appear in no prompt module's required inputs. Annual revenue is asked as a free-text optional field when the same figure is far better sourced from accounting — and asking for it early, before trust exists, is the kind of question that makes people abandon a form.

**f) Questions that matter are missing.** Currency is hardcoded to OMR. Nothing asks whether the customer intends to actually work inside the NEXUS CRM — which, as section 4 shows, determines whether half the product ever functions. Nothing asks for consent to index uploaded documents. Nothing asks who should receive the daily brief.

---

## 3. The data-source truth table

For every headline capability: what actually feeds it, and whether it works at each level of customer supply.

**Legend:** ✅ works · ◐ partial, honestly labelled · ❌ nothing to show

| Capability | Real data source | Website only | + Documents | + GA4/GSC | + CRM used | + Accounting |
|---|---|---|---|---|---|---|
| **Business audit — Brand** | Crawled site content | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Business audit — SEO** | DataForSEO + Search Console | ◐ market data only | ◐ | ✅ | ✅ | ✅ |
| **Business audit — Customer experience** | Google Business Profile reviews | ◐ if listed | ◐ | ◐ | ✅ | ✅ |
| **Business audit — AI readiness** | Crawl + PageSpeed | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Business audit — Marketing** | GA4 | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Business audit — Sales** | CRM | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Business audit — Operations** | *no source in architecture* | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Competitor discovery** | Search + Maps + SEO domains | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Competitor ad monitoring** | Meta Ad Library | ✅ | ✅ | ✅ | ✅ | ✅ |
| **SEO Intelligence** | DataForSEO | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Growth Planner** | Pure generation on profile | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Content Studio** | Pure generation | ✅ | ✅ | ✅ | ✅ | ✅ |
| **HR policies & SOPs** | Pure generation on templates | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Lead Intelligence** | Search/Maps/directories + Apollo | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Opportunity Radar (tenders)** | Tender feed | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Proposal Studio (real prices)** | RAG over uploaded price list | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Company Brain Q&A** | RAG over uploads | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Website traffic KPI** | GA4 | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Total leads KPI** | NEXUS CRM | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Conversion rate KPI** | GA4 ÷ CRM | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Sales revenue KPI** | Accounting, or CRM deals won | ❌ | ❌ | ❌ | ◐ won deals only | ✅ |
| **ROI KPI** | Revenue ÷ ad spend | ❌ | ❌ | ❌ | ❌ | ◐ needs ad spend too |
| **Customer LTV** | CRM history over time | ❌ | ❌ | ❌ | ◐ after ~6 months | ✅ |
| **Morning brief (deltas)** | All of the above × 2 periods | ❌ | ❌ | ◐ from week 2 | ✅ from week 2 | ✅ |
| **Company Health Score** | Everything | ◐ 3 of 7 depts | ◐ 3 of 7 | ◐ 4 of 7 | ◐ 5 of 7 | ◐ 6 of 7 |
| **Pipeline risk / stale deals** | CRM activity timestamps | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Customer health / churn** | CRM activity + reviews | ❌ | ❌ | ❌ | ◐ needs history | ✅ |
| **Finance Advisor** | Accounting API | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Business Simulator** | Revenue, margin, cost data | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Decision Intelligence** | Google Ads timeseries | ❌ | ❌ | ❌ | ❌ | ◐ needs Ads too |

### Read the table two ways

**Column 1 (website only) is the honest day-one product:** 11 capabilities fully working, 3 partial, 17 empty. Everything that works is *outside-in* — derived from the public internet plus generation. Everything empty is *inside-out* — it needs the customer's own operating data.

**Two rows never fill in, at any level.** Operations and People have no data source anywhere in the architecture or the prompt library. The prototype shows Operations 88 and People 84. Nothing in the entire integration inventory could produce those. They are decorative, and they should either be removed from the health score or given a real input — SOP and task completion rates from inside NEXUS for Operations; a lightweight headcount/capacity input for People.

---

## 4. So who serves the KPI?

There are exactly four possible sources. There is no fifth, and the AI is not one of them.

**1. Connected third-party systems** — GA4, Search Console, accounting, Google Ads.
The cleanest data, the highest friction. Also the least reliable assumption in the GCC SME market: plenty of target customers have no GA4 property properly installed, and cloud accounting adoption is far from universal. Planning as though OAuth will be granted is planning on hope.

**2. The NEXUS CRM — the only first-party source the product controls.**
Leads, pipeline value, deals won, stage changes, activity recency, lead source, conversion. This is the one data source that doesn't depend on the customer having bought something else first.

> **This reframes the CRM entirely.** In the source documents the CRM is listed as one module among twelve, and explicitly described as "standard structured data, not an AI feature." That undersells it. The CRM is the data acquisition strategy for the whole executive layer. If the customer doesn't work in it, the Morning Brief, the Health Score's sales and revenue departments, pipeline risk, churn prediction and LTV all have nothing to say — forever. CRM adoption is therefore the single most important activation metric in the product, well above login frequency.

**3. Manual entry.**
The business-model document rules this out: KPIs should come from real systems "rather than manual entry." That is the right instinct for a mature product and the wrong call for MVP. An owner typing last month's revenue takes ten seconds and unlocks the finance view, margin analysis and eventually the simulator. Refusing it on purity grounds means choosing an empty dashboard over a slightly less rigorous one. The correct design is to accept manual figures, **label them visibly as self-reported**, and keep them clearly separated from API-sourced figures in both the UI and the audit trail.

**4. Public and market data.**
Keyword volumes, competitor ads, reviews, tenders, directory listings. Genuinely real and genuinely useful — but it describes the *market*, never *them*. No amount of it will ever produce "your revenue is up 12.7% this week."

**And the non-answer:** the AI. It cannot supply any of these without breaking the rule the entire product is built on. Every prompt module in the library says so explicitly. This is worth stating plainly to the team, because under launch pressure "just have the model estimate it" is exactly the shortcut someone will propose.

---

## 5. What the flow should be instead

The fix is not fewer questions. It is **asking for things in the order that value is delivered**, so each request is justified by something the user has just seen.

### Stage 0 — One field, sixty seconds
Ask for the **website URL**. Nothing else. Start the crawl.

### Stage 1 — Show the audit before asking anything else
Brand, SEO, customer experience and AI readiness scored from the crawl, PageSpeed, reviews and keyword data — with the three departments that need connected data shown as locked, not as scores. Plus the discovered competitor list.

This is real, it is about their business, and it costs the user one field. It is the only moment in the flow that earns the right to ask for the rest.

### Stage 2 — Confirm, don't collect
Present what the scan found — services, segments, market, tone, competitors — as editable chips. Confirming or correcting eight extracted facts is a fraction of the effort of typing them, and the result is more accurate.

### Stage 3 — Ask only what cannot be inferred
| Question | Why it can't be inferred | Used by |
|---|---|---|
| Ranked business goals | Intent, not published | Growth Planner, prioritisation of every recommendation |
| Biggest challenges | Intent | Audit roadmap ordering, brief prioritisation |
| Ideal customer, in their words | Often differs from who they currently serve | Lead Intelligence, targeting |
| Average deal size | Rarely published | Pipeline value, forecast, simulator |
| Monthly marketing budget | Never published | Channel and budget allocation |
| Number of salespeople | Not on most sites | Capacity, forecast realism |
| Which competitors they actually worry about | Search rankings surface a different set | War Room monitoring list |
| Words to avoid / must-use | Tone is inferable; prohibitions are not | Every generative module |
| Currency and financial year | — | Every figure in the product |
| Who receives the daily brief | — | Delivery |

**Drop from onboarding:** phone number (used by nothing), branch count (used by nothing), annual revenue as a typed field (sensitive, better sourced from accounting, ask later). **Defer:** logo upload — needed for proposals and ad creative, not for onboarding.

### Stage 4 — Connections, one at a time, each with a stated unlock
Not five bundled groups. Individual cards, in ascending order of friction, each naming exactly what it turns on:

- *Connect Google Analytics → unlocks traffic, conversion and the Marketing health score*
- *Connect Search Console → unlocks real ranking data in SEO Intelligence*
- *Connect Google Business Profile → unlocks review monitoring and customer health*
- *Import or start your CRM → unlocks pipeline, forecast, the Morning Brief and Sales health*
- *Connect accounting → unlocks margin, cash flow, Finance Advisor and the Simulator*

Every one skippable. Every one re-offered later from the exact place in the product where its absence is felt — a locked tile is a better conversion surface than an onboarding step.

### Stage 5 — Documents, framed by outcome
"Upload your price list → Proposal Studio quotes real prices with citations." "Upload past proposals → it matches your structure." Include the consent statement here: documents are indexed for this workspace only and are not used to train third-party models.

### Stage 6 — Team, last
The least urgent step, and the one most likely to be done later anyway.

---

## 6. The zero-data dashboard must be designed, not empty

This is the deliverable that is currently missing entirely, and it is the one that decides whether a customer who skips everything churns in week one.

**Rules for it:**

1. **Every locked tile states its unlock.** Not a spinner, not a zero. "Revenue — connect accounting or log your first deal." The tile is a call to action, not a failure.
2. **The health score shows its denominator.** "68/100 across 4 of 7 departments" — never a whole-business score computed from half the evidence. The unscored departments are listed with what they need.
3. **Week one is a baseline, not a brief.** A morning brief is deltas, and in week one there is no prior week. Shipping the brief on day one guarantees generic filler — precisely the failure the grounding rules exist to prevent. Week one shows "here is your starting position"; the brief begins in week two and says so.
4. **Self-reported figures are visibly marked** and never silently mixed with API-sourced ones.
5. **A visible data-completeness meter.** "You're using 6 of 21 capabilities — 3 connections away from the full executive view." This makes the gap legible and actionable instead of confusing.
6. **The outside-in half is promoted, not padded around.** With zero connections the user still gets a real audit, a real competitor set, real keyword data, a real marketing plan and unlimited content. Lead with that rather than surrounding it with empty executive tiles.

---

## 7. What this changes in the plan

| Area | Current position | Should become |
|---|---|---|
| CRM | One module of twelve, "not an AI feature" | The data acquisition engine; adoption is the top activation metric |
| Manual entry | Ruled out | Allowed at MVP, visibly labelled as self-reported |
| Onboarding | 11 steps, value at the end | Value at step 1, questions justified by what was shown |
| Connections | One bundled step, five groups | Individual, unlock-labelled, re-offered contextually in-product |
| Health score | 7 departments, always scored | Scored departments only, denominator shown; Operations and People need a real input or removal |
| Morning Brief | Ships day one | Ships week two; week one is a baseline artifact |
| Empty states | Not specified | A designed zero-data dashboard is an MVP deliverable, not polish |
| Success metric | Onboarding completion ≥ 70% | Add: connections per account, CRM-active accounts, capabilities unlocked by day 30 |

---

## 8. The uncomfortable question this raises

If a meaningful share of customers connect nothing and never adopt the CRM, then for those customers NEXUS OS is an audit, a competitor tracker, an SEO tool and a content generator — a good product, but not an operating system, and priced against a different set of competitors.

That is not an argument against building it. It is an argument for knowing which product a given customer is actually buying, measuring the split honestly, and deciding deliberately whether the answer is to price the two differently, or to make CRM adoption a condition of onboarding rather than an option within it.

Design-partner customers in Phase 0 will answer this cheaply, and it is the single most valuable thing Phase 0 can find out.
