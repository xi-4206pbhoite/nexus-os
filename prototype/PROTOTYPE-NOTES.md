# NEXUS OS — client demo prototype

**`nexus-os-prototype.html`** — one file, the whole journey. No build step, no
server, no network. Double-click to open; send the file to share it.

It lives in `prototype/`, deliberately outside `apps/web/`, and must stay there.

---

## 1. The journey it covers

```
Landing page  →  preview audit  →  sign up  →  onboarding (7 steps)
              →  sign in as one of eight people
              →  that person's own workspace  →  admin portal
```

Deep links via the hash: `#landing`, `#signup`, `#onboarding`, `#signin`, or a
person's id — `#layla`, `#omar`, `#huda`, `#yousuf`, `#mariam`, `#fatma`,
`#salim`, `#nadia`.

---

## 2. The idea it exists to explain

**The dashboard is the person.** You sign in as somebody and their department is
the entire application — their navigation, their layout, their vocabulary. A
Sales manager has no Finance entry greyed out in the sidebar, because Finance was
never part of their product. Navigation is assembled per user, not filtered per
user.

Two consequences worth pointing at:

- **Each department workspace is structurally different**, not one grid with the
  labels swapped. Sales gets a pipeline board. Finance gets ageing buckets and an
  approvals queue. Operations gets a dispatch lane board. They share the metric
  tile and almost nothing else.
- **A Contributor gets a genuinely smaller product** — "my day, my deals, my
  accounts, my targets" — rather than a manager's page with holes cut in it. That
  is what `contributor_restricted` in `scopes.py` actually means, and it reads as
  a deliberate design rather than a punishment.

---

## 3. What this is not

Not the application. No API, no database, no authentication, no permission
enforcement. Nothing typed into it is saved or sent. Signing in as a persona is a
demo device; real scoping happens in Postgres row-level security and
`retrieval/`, none of which is involved here.

---

## 4. Every number in it is invented

The product sells on **never invent a number** (invariant I1). This file violates
that throughout, which is only acceptable because the repo's content rule permits
mocks provided they are visibly tagged. So:

- a fixed banner marks the whole file as demo data and cannot be dismissed
- every metric tile and every panel carries an `ILLUSTRATIVE` marker
- the demo company, **Nakhla Trading LLC**, is fictional
- competitors are anonymised as "Competitor A–D" rather than named, because
  inventing a real company's pricing move is exactly the fabricated claim the
  product refuses to make
- no real customer, logo, testimonial, price or result appears anywhere

Two places carry a green **"Real — from the built model"** chip instead: the
role/reach table in onboarding and the sensitivity lattice. Those come from
`app/domain/scopes.py` and are accurate. Everything else is not.

**Do not copy figures from this file into a proposal or a deck.**

---

## 5. The eight people

| Person | Role | Their application | Never sees |
|---|---|---|---|
| Layla Al-Amri | Owner | Chief of Staff: morning brief, business health, all departments, decisions, Company Brain, admin | L4 items she is not named on |
| Omar Al-Balushi | Executive | Strategy: opportunities, competitors, market signals, strategic bets, plus cross-department read | L4 items he is not named on |
| Huda Al-Kindi | Dept manager | Marketing: overview, channels, content, campaigns, enquiries | Every other department. Her Enquiries table has no deal-value column, on purpose |
| Yousuf Al-Harthy | Dept manager | Sales: overview, pipeline board, accounts, my team, forecast | Every other department |
| Mariam Al-Saidi | Contributor | Sales, her own slice: my day, my deals, my accounts, my targets | Any department total, and every other department |
| Fatma Al-Zadjali | Dept manager | Finance: overview, cash, receivables, payables, approvals | Every other department. Salary detail stays L4 even for her |
| Salim Al-Rawahi | Dept manager | Operations: overview, dispatch board, stock, suppliers | Every other department. No revenue, no margins |
| Nadia Al-Busaidi | Dept manager | People: overview, hiring, people, leave | Individual salaries — she manages People and still cannot open one |

---

## 6. Suggested walkthrough

| # | Do this | The point to make |
|---|---|---|
| 1 | Landing → **Analyse my business** | A reduced audit arrives before any account exists. The score reads **69 across 3 of 10 categories** — never a whole-business number built from part of the evidence. |
| 2 | The seven locked tiles beneath it | Missing data is shown as *locked with the step that unlocks it*, never as a zero. A zero would read as a real, bad result. |
| 3 | **Claim this audit** → onboarding **step 2** | The DNS TXT record. This is the trust step: until the domain is verified NEXUS will not name competitors or pull keyword data, because anyone can type a rival's address. |
| 4 | Onboarding **step 6, invite team** | The role table is real. Point out that L4 is absent: no role reaches it, not even the Owner's. It is reached only by being named on the item. |
| 5 | Finish → lands in **Layla's** Chief of Staff | The morning brief says what changed, what it means, what to do — each with its source named. This is the product; the tiles below are supporting evidence. |
| 6 | Any tile → **"+ why this number"** | Opens the method, the inputs and the arithmetic. This is what "every number is auditable" means in practice. |
| 7 | Switch person → **Yousuf** → Pipeline | A sales tool. Clay edge on anything silent longer than *their own* median cycle — not a generic 30-day rule. |
| 8 | Switch person → **Mariam** | The strongest moment. Same department, completely different application: a day list, her five accounts, her own target. No lock icons, no gaps — plus a card explaining *why* there is no pipeline total. |
| 9 | Switch to **Salim** → Dispatch board | Nothing like either sales screen. Four lanes, two late orders named. NEXUS will not report "88% on time" unless it can also say which 12% were not. |
| 10 | Switch to **Nadia** → People | She manages People and the compensation column is still L4. A job title does not name you on an item. |
| 11 | Back to **Layla** → Admin portal → Audit log | Refusals are logged as well as successes, and the log is Owner-only — a log everyone can read is a second copy of the data it audits. |

---

## 7. What it gets right about the real model

Faithful to what is actually built, and the reason this is a teaching tool rather
than a pretty picture:

- **Scores carry their denominator.** `across 3 of 10`, `across 5 of 6`.
- **Locked ≠ zero.** Every unavailable category names its unlock.
- **Composite only over full coverage**, and the copy says so.
- **Contributor is not Manager.** No department-wide aggregate appears anywhere
  in Mariam's application — correction #2 in `scopes.py`.
- **L4 by naming, not by role.** No persona reaches an L4 item, including the
  Owner and including the People manager on salaries.
- **Cross-department separation**, verified by walking all 38 sections across all
  eight personas: no department persona's screens contain another department's
  headline figures.
- **Honest states.** No blank panels, and no zeros standing in for "not
  connected" or "you may not see this".
- **Stale is stale.** A connector that has not synced is labelled, not silently
  reused.

### Verified in-browser

Landing, preview audit, sign-up, all 7 onboarding steps, the persona picker, and
38 sections across 8 personas. Plus both exit paths, and a stale `#app` deep link
with nobody signed in, which falls back to the picker rather than dead-ending.
Console clean throughout.

---

## 8. Milestone debt this deliberately runs ahead of

`CLAUDE.md` says one milestone at a time, stop and wait for validation. This
prototype spans M4 through M13 and stops at none of them. That is a conscious
trade for a client conversation, not a change of plan. **Nothing here counts as
progress against doc 07**, and none of it should be lifted into `apps/web`
without the work below.

| Screen | Milestone | Still owed before it can ship for real |
|---|---|---|
| Sign up, sign in | M1/M3 | Session cookies, CSRF on every mutation, email verification wired to the real mailer. Backend exists; no UI. |
| Onboarding, domain claim | M3/M4 | TXT check against real DNS, ephemeral→verified workspace transition, claiming the preview. Backend exists; no UI. |
| Document upload | M5 | Classification-default-deny passes server-side; the review queue UI does not exist. |
| All eight workspaces | M7–M9 | **No data source exists.** GA4, CRM, accounting and HRIS connectors are unbuilt, so every figure would render as a locked state today. |
| "Why this number" trails | M6 | Real calculators with real inputs. `calculators/` holds the Preview audit only. |
| Per-person navigation | M1 | The nav must be derived server-side from the session's scope. Assembling it in the client is a convenience, not a boundary. |
| Admin portal | M13 | Impersonation with time-boxing and reason logging, access-controlled audit log, deletion fan-out across embeddings, cache, storage and artifacts. |

### Tests owed before any of this becomes real UI

Per doc 07 §5.3, for anything touching permissions or grounding the test comes
**before** the feature:

1. A rendered dashboard must never show a composite score without its
   denominator — assert on the DOM, not the payload.
2. A locked category must never render as `0` or as an empty tile.
3. A Contributor session must not *receive* department aggregates in the API
   response, not merely have them absent from the UI. A navigation tree built in
   the client is not a permission boundary.
4. The section list returned for a session must contain only sections that
   session's scope permits — the per-person navigation needs its own test.
5. A stale connector must render as stale rather than silently reusing its last
   good value.
6. The admin audit log must 403 for every role except Owner.

---

## 9. Known cosmetic gaps

- The four-column pipeline and dispatch boards drop to two columns below 1000px
  and are cramped on a phone. Fine for a laptop demo.
- Charts are hand-rolled inline SVG so the file needs no CDN. Deliberately
  simple; the real product should use a charting library.
- Web fonts load from Google Fonts. With no internet it falls back to Georgia and
  system sans — acceptable, not identical.
