# NEXUS OS — Flow Interrogation

**Purpose:** everything that must be decided before the new flow in `doc/09` can
become a detailed build plan. 71 questions across eleven stages.
**Date:** 25 August 2026 · **Status:** awaiting Parul's answers

**How to answer.** Every question carries my recommendation. Answer by exception —
say **"agree"** for a block and correct only the ones you want differently, e.g.
*"agree §1–§3, except 12: allow several companies"*.

**Priority markers.** 🔴 blocks the phase plan · 🟠 blocks a stage's build ·
🟡 blocks a screen or a detail · ⚪ can be answered during the phase that needs it

---

## §1 · Stage 0 — Landing page

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 1 | 🔴 Does the landing page keep a URL capture field? *(D18)* | It is the only working end-to-end flow today and 90% of it is reused by research either way | **Keep it as a signup lead-in.** Enter URL → crawl starts → signup form appears. The audit is shown after registration as the first thing in the Brain |
| 2 | 🟠 Is there plan or pricing selection before signup? | A3 assumes a trial flag and no paywall. If a plan is chosen up front, the whole billing surface enters MVP | **No.** Trial flag at company creation, pricing page informational only |
| 3 | 🟠 Do Privacy and Terms pages exist before we open public signup? | They were deliberately removed rather than pointed at nothing. Accounts can now be created | **Yes, before public signup.** Not before a design partner behind a link |
| 4 | 🟡 Does the landing page's capability list get trimmed to what exists? | 35 named features against zero delivered offerings. The CLAUDE.md content rule forbids invented results but says nothing about naming unbuilt features | **Trim to seven pillars plus "and more coming".** Naming 35 features we cannot show is the same trust problem one layer up |
| 5 | ⚪ Is there a public demo or sandbox workspace? | Changes whether we need seeded demo data, which collides with "no mock data in the running app" | **No.** A recorded walkthrough instead |

---

## §2 · Stage 1 — Sign up and log in

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 6 | 🟠 Email + password only, or Google sign-in too? | Google OAuth arrives anyway for GA4. Reusing it for sign-in is cheap and removes the password-reset surface for most users | **Both, Google first.** Password as fallback. Reuses the OAuth client D3 unblocks |
| 7 | 🔴 Is email verification **blocking** or **non-blocking**? | Blocking means the user waits for an inbox mid-flow. Non-blocking means an unverified account can build a Brain | **Non-blocking.** Verify to invite members or connect a tool — the same gate D19 proposes for the domain |
| 8 | 🔴 Someone signs up with an email whose domain **already has a workspace**. What happens? | This is the difference between one workspace per company and one per employee. It is absent from the sketch and it decides whether the product spreads inside a company or fragments | **Offer "request to join" as the primary action**, with "create a separate company" secondary and warned. The request goes to that workspace's Owner as an approval |
| 9 | 🟠 Can one person belong to several companies? | The `membership` table is many-to-many from day one and the agency case depends on it. But the new flow has no workspace switcher | **Yes, keep M:N.** Add a switcher in the header once a second membership exists — hidden until then |
| 10 | 🟠 Is password reset in MVP? | Neither layer has it. Every real signup flow needs it within days of launch | **Yes.** Same token machinery as email verification, so it is small once C10 lands |
| 11 | 🟡 Session length — is 12 hours right? | Currently 12h with no idle timeout and no refresh | **Keep 12h, add a rolling refresh on activity.** No idle timeout at MVP |

---

## §3 · Stage 2 — Register the company

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 12 | 🟠 Exactly which fields? | Each one is either a question we never have to ask again or friction at the highest-drop-off moment | **Five:** company name · website URL · country · reporting currency · headcount band. Industry is inferred from the crawl and confirmed at the review gate |
| 13 | 🔴 Is the website URL **mandatory**? | A GCC SME with only an Instagram page is a real case, and the whole research stage keys off this URL | **Mandatory but with an escape:** "I don't have a website" → the Brain is built from documents and questions only, and the dashboard says which tiles that costs |
| 14 | 🔴 Where exactly does domain verification gate? *(D19)* | The one hard conflict in the sketch — see `doc/09` §4.1 | **Gate the exclusive claim, inviting members, and connecting company-data tools. Not workspace existence** |
| 15 | 🟠 What if the website domain does not match the signup email domain? | A founder signing up with Gmail for `acme.om` is normal in this market | **Allow it.** It just means the EMAIL verification method is unavailable to them — DNS TXT or file-at-path only |
| 16 | 🟡 Can one company own several domains? | Multi-brand and regional TLDs (`.om` plus `.com`) are common | **One primary domain at MVP**, additional domains as a post-MVP settings feature |
| 17 | 🟠 Can a user create more than one company? | Affects the header, the switcher, and whether "register a company" is a one-time flow or a repeatable action | **Yes, but not during onboarding.** One at signup; more from the switcher later |
| 18 | 🟡 Trial length, and what happens at the end? | A3 says trial flag only, but "the trial ended" still needs a screen | **30 days, read-only afterwards**, nothing deleted |

---

## §4 · Stage 3 — Company questions and department selection

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 19 | 🔴 How many questions before the department blocks? | Doc 08 §1 has ~7 company questions; doc 06 §2.5 has 14. Together with up to 7 department blocks of 9 that is 70+ questions | **Five company questions**, and only ones a crawl cannot answer: what you sell · ideal customer · top three goals · biggest challenges · fiscal year start |
| 20 | 🔴 Do we ask, or crawl-then-confirm? | Doc 04's central argument is that every question a crawler could answer is a tax on the moat | **Crawl-then-confirm wherever possible.** Ask only what is not on the website. Everything else appears at the review gate as a fact to correct, not a blank field |
| 21 | 🟠 Which questions are mandatory? | A mandatory question is a wall; an optional one is often skipped and the Brain is thinner | **None mandatory except the five in 19**, and each of those has a "not sure yet" that becomes an assumption at the review gate |
| 22 | 🔴 Department selection — from the fixed seven, or can they name their own? | Custom departments break the seven-director model, the scope lattice's `Department` enum, and every dashboard spec | **Fixed seven.** A free-text "anything else?" is captured as a Brain fact, not as a department |
| 23 | 🟠 What if they select all seven, or only one? | Selecting all seven recreates the empty-dashboard problem the new flow exists to solve | **Recommend three to five and say why**, but allow any number. One is fine |
| 24 | 🟡 Is "Chief of Staff" selectable, or automatic? | It is a synthesis layer over the others, not a department a company runs | **Automatic and always present** for Owner/Executive. Never in the selection list |
| 25 | 🟠 Single reporting currency, or multi? | Multi-currency touches every calculator and every number on every dashboard | **Single at MVP**, declared here, everything converted for display later |
| 26 | 🟡 Do we ask headcount here or in the People block? | It sizes the People department and the plan tier | **Here** (question 12) — it is a company fact, not a departmental one |

---

## §5 · Stage 4 — Per-department questions

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 27 | 🔴 Does the founder answer **all** selected departments' blocks, or only their own? | Doc 08 says the owner answers the selected departments' questions. Five departments × 9 questions is 45 questions in one sitting | **Answer their own department now; defer the rest.** Each unanswered block shows on its director as "answer 9 questions to turn this on" — and an invited manager can answer it instead |
| 28 | 🟠 Can a department block be skipped and filled later? | Determines whether onboarding is a funnel or a gate | **Yes, always.** Progress saved per block, resumable |
| 29 | 🟠 Does an unanswered department still get a dashboard? | Otherwise selecting a department produces nothing at all | **Yes** — with its tiles in a named state pointing at the questions that unlock them |
| 30 | 🟠 Who may answer department-scoped questions? *(D16)* | Today: Owner and Executive only, by default-deny | **Widen to that department's Manager.** Contributors confirm, never assert |
| 31 | 🔴 Does a member's answer bind the department or only themselves? *(D22)* | Two Sales managers can disagree about average deal size, and precedence has nothing to say about one user over another | **Manager binds; Contributor proposes.** A proposal appears at the review gate for the Manager or Owner to confirm |
| 32 | 🟡 What happens to a person's answers when they change department? | M5's superseded-document problem in a different shape | **Answers stay tagged to the department they were given for**, and the new department's block is offered fresh |
| 33 | ⚪ Are doc 08's ~9 questions per department the final set? | They are extracted from the prototype, not designed against the calculators that will consume them | **Use them as the starting set**, and cut any question no calculator or Brain fact consumes |

---

## §6 · Stage 5 — Document onboarding

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 34 | 🔴 Is uploading a document **required** to proceed? | Proposal Studio and pricing work need a price list. But requiring a document at signup will lose people | **Not required, strongly guided.** Show what each document type turns on, and let them proceed with none |
| 35 | 🟠 Which document types do we ask for, per department? | "Upload your documents" with no guidance gets nothing uploaded | **Three named asks per selected department**, e.g. Sales: price list, a past proposal, the services list. Named beats generic every time |
| 36 | 🟠 Limits — per file, per upload, per workspace? | Storage cost, parse cost, and the size cap is already enforced but arbitrary | **25 MB per file, 20 files at onboarding, 500 MB per workspace at MVP** |
| 37 | 🟡 Which formats? | PDF, DOCX, PPTX, XLSX are built. CSV and images are not | **Add CSV** (price lists arrive as CSV constantly). **No images at MVP** — that needs OCR |
| 38 | 🟠 Scanned PDFs fail visibly and there is no OCR *(A7)*. Acceptable? | In this market a scanned price list or trade licence is very likely | **Accept for MVP but count it.** If design partners hit it often, OCR becomes a fast follower |
| 39 | 🔴 When does the founder review the review queue? | Every chunk currently withholds to L5 + review. If the founder must clear a queue mid-onboarding, the flow stalls | **Their own uploads auto-approve for themselves** (they are the uploader; L5 already means uploader-only). The queue is for what becomes *workspace-visible*, and it is reviewed at the review gate in stage 8 |
| 40 | 🟠 Who signs off the consent and right-to-use wording? | It is a legal warranty the customer gives us, and it is versioned in the schema already | **You do, with a lawyer, before public signup.** A placeholder version string is fine for design partners |
| 41 | 🟡 Can a document be replaced later, and does that re-run classification? | Task 5.10 says supersede re-runs classification; the code path violates a check constraint today | **Yes, replace re-runs everything.** Fixed in Phase 1 |

---

## §7 · Stage 6 — Connect tools

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 42 | 🔴 Which tools appear on this screen at MVP? | The screen is the flow's biggest conversion lever, and every entry is a connector to build | **Four: GA4 · Search Console · one CRM · accounting (if D7 says so).** Nothing else |
| 43 | 🔴 Which CRM? *(D10)* | Decides whether stale-deal detection exists at all, via `last_activity_at` | **Zoho**, on the stated GCC-prevalence assumption — but confirm with the first design partner before building |
| 44 | 🔴 Do we show tools we cannot connect yet, marked "coming soon"? | Directly tests the honesty rule at the highest-visibility moment | **No.** The screen shows only what genuinely connects. If nothing does, the stage is skipped entirely and never rendered |
| 45 | 🟠 Is connecting a tool gated on domain verification? | Part of D19. A tool holds company data, so an unverified claimant connecting a CRM is a real risk | **Yes, gated.** This is the strongest argument for D19's placement |
| 46 | 🟠 What happens on skip — where do we ask again? | Skipping must not mean never | **A persistent "connect a source" affordance on every affected tile**, plus one reminder in the Baseline. No nag modals |
| 47 | 🟡 Read-only scope at MVP confirmed? *(A5)* | CRM write is a much heavier permission ask | **Yes, read-only.** Write is a separate, later, explicit request |
| 48 | ⚪ Who owns a connection — the person who made it, or the workspace? | If the person leaves, the connection dies with them unless it is workspace-owned | **Workspace-owned, with the connector recorded**, and re-auth prompted when the token dies |

---

## §8 · Stage 7 — Full research and the Brain

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 49 | 🔴 Research budget — pages, duration, cost ceiling? *(D20)* | Decides whether stage 7 is a settling step or a wall, and it is a recurring cost line | **20 pages, 5-minute soft cap, hard stop at 10.** Per-source failure surfaced individually |
| 50 | 🔴 Is research resumable across sessions? | A founder will close the tab. Without resumability they restart from nothing | **Yes.** `research_run` persists; reopening shows progress or the finished gate |
| 51 | 🔴 What if the site is JavaScript-rendered and the crawler sees an empty shell? | Very common, and the crawler does not execute JS | **Detect and say so**, then fall back to questions and documents. Headless rendering is a post-MVP decision with real cost and SSRF implications |
| 52 | 🟠 Where do competitors come from? | Discovery needs a SERP source; user-entered is free and often better | **Ask for up to three at the review gate, pre-filled from whatever discovery finds.** The user knows their competitors better than a SERP does |
| 53 | 🟠 Keyword data — DataForSEO now, or Locked? *(D2)* | Doc 05 §3.7 forbids estimating volumes | **Locked until you have credentials.** Do not estimate, do not proxy |
| 54 | 🟠 How often does research re-run? | The Brain must not go stale, but every run costs money and crawls someone's site | **Weekly for the crawl, on-demand otherwise**, and a contradicting fact raises re-confirmation rather than overwriting |
| 55 | 🟠 Is there a per-workspace research quota? | Otherwise one workspace can spend the crawl and API budget | **Three manual re-runs per month at MVP**, plus the weekly automatic one |
| 56 | 🔴 If research fails entirely, can the user still reach the dashboard? | Otherwise a bad website blocks the product | **Yes.** The Brain contains whatever succeeded, the dashboard says what is missing, and research can be retried |
| 57 | 🟡 Does the user see research progress per source, or one spinner? | A five-minute spinner reads as broken | **Per source, with each one's outcome** — succeeded, failed with a reason, still running |

---

## §9 · Stage 8 — The review gate

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 58 | 🔴 Must the review gate be completed to reach the dashboard? | It is where corrections enter the Brain — the compounding asset — but a wall here loses people at the finish line | **No, but it is the default landing.** Unreviewed facts are marked unconfirmed wherever they are used |
| 59 | 🔴 How many facts do we show? | A 200-row review screen is unusable and will be dismissed wholesale | **Group into 6–8 themes, show the ~20 highest-impact facts, and let them expand.** Impact = how many capabilities depend on the fact |
| 60 | 🟠 Can they bulk-accept? | Bulk-accept is honest if the facts are visible; it is a lie if it hides them | **Yes, per theme, after the theme is expanded.** Never a single global "accept all" |
| 61 | 🟠 What happens to facts never reviewed? | The difference between a confirmed and an inferred fact is the whole precedence model | **Used, but labelled inferred**, and the tile that uses one offers a one-click confirm |
| 62 | 🟡 Can a user delete a fact rather than correct it? | Some inferences are simply wrong and have no correct value | **Yes, with a reason**, and a deleted fact is not re-inferred by the next crawl without re-confirmation |

---

## §10 · Stage 9 — Dashboard

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 63 | 🔴 Does department selection restrict which directors exist? *(D21)* | Decides whether an unselected department is invisible or merely empty | **Restrict, with an explicit "add a department" action.** Seven half-empty directors is what the new flow exists to avoid |
| 64 | 🔴 The composite score's denominator is now variable — is that right? | This **re-opens D8.** With departments selected per company, the denominator is *the selected scoreable departments*, not a fixed six | **Derive it.** Build a capability registry where each capability declares its required sources, and compute both the score denominator and the completeness meter from it. Then the number self-corrects |
| 65 | 🔴 Finance — which of D7's three options? | Every doc 05 §5 widget needs the accounting API, which is out of scope | **Manual entry, visibly labelled self-reported.** Doc 04 §7 already sanctions it and doc 04 §6 rule 4 constrains it |
| 66 | 🟠 What is the landing view after onboarding? | First impression of the built product | **Chief of Staff for Owner/Executive** (Baseline, not Morning Brief, in week 1); **their own department** for everyone else |
| 67 | 🟡 Does the assistant panel appear from day one as an empty state? | Retrofitting a persistent side panel into seven finished dashboards is a rewrite of all seven | **Yes, reserved from the first dashboard**, rendering an honest empty state naming what it will do |

---

## §11 · Stage 10 — Members

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| 68 | 🟠 Who can invite? *(D16)* | Today Owner and Executive only, by default-deny | **Widen to Department Managers for their own department only.** `outranks` already prevents granting a role above your own |
| 69 | 🟠 Does an invited member's onboarding block their dashboard? | A nine-question block between a new user and the product they were invited to see | **No.** Show the dashboard, with the questions as the first thing on it |
| 70 | 🟡 Can a member belong to more than one department? | `membership.departments` is already an array, so the data supports it | **Yes, up to three.** Common in small companies where one person wears several hats |
| 71 | 🟠 What happens to a member's L5 documents when they leave? | L5 is uploader-only. If the uploader is gone, the content is unreachable by everyone, including the Owner | **On revocation, offer the Owner a logged transfer of ownership.** Never silent reassignment, never silent deletion |

---

## §12 · Cross-cutting

| # | Question | Why it matters | My recommendation |
|---|---|---|---|
| C1 | 🟠 What is in Settings at MVP? | Everything with nowhere else to live ends up here | **Five sections:** company profile · domain verification · connected tools · members and roles · data export |
| C2 | 🟠 Are data export and deletion in MVP? | A GDPR-shaped commitment, and the fan-out is wide: embeddings, cache, snapshots, storage, artifacts | **Export yes** (it is cheap and it builds trust); **full deletion fan-out at M13** |
| C3 | 🟠 What email does the product send, and how often? | Verification, invitations, the Baseline or Morning Brief, staleness alerts | **Three at MVP:** verification, invitation, and a weekly digest. No daily email until the Brief is real |
| C4 | 🟡 Mobile — responsive only, or a dedicated capture flow? | Doc 05 §6c wants mobile Ops capture: progress, issues, photos on site | **Responsive everywhere; a dedicated mobile capture view for Operations only**, at M11 |
| C5 | 🟠 English only at MVP? | Arabic is out of scope, but the market is bilingual and RTL is not a late-stage retrofit | **English only, but no hardcoded strings in components** — so Arabic is a translation job later, not a rewrite |
| C6 | 🔴 Who is the first design partner, and when do they see it? | It decides which department to build first, which CRM to pick, and whether the question set survives contact | **Name one before Phase 2.** Half these recommendations are guesses that one real customer would settle |
| C7 | 🟠 Is there an internal admin console at MVP? | Without it you cannot see tenant health, AI spend, or why a customer's research failed | **A minimal one at Phase 3:** workspaces, research-run status, error rates. Impersonation waits for M13 |
| C8 | 🟡 What is the target time from signup to review gate? | It is the number the whole flow design is optimising, and it should be measured | **Twenty minutes**, with the crawl running in the background from stage 2 |

---

## §13 · The questions I could not put a recommendation against

These are business calls where I have no basis to guess.

| # | Question |
|---|---|
| B1 | What does a company pay, and is it per workspace or per seat? The $49/month in the source material is explicitly flagged as unvalidated |
| B2 | Is there a services or setup component — do you onboard customers yourself at first, or is it fully self-serve from day one? |
| B3 | What is the target segment for the first ten customers, specifically enough to choose a CRM and a first department? |
| B4 | What is the acceptable monthly infrastructure and AI cost per customer? The source material says ~$260/month total at validation volume, which is a platform figure, not a per-tenant one |
| B5 | Is there a hard launch date or event this is building towards? |
