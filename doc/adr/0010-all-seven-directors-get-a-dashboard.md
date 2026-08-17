# 0010 — All seven directors get a dashboard

- **Status:** Accepted
- **Date:** 18 August 2026
- **Decider:** the user — *"all seven departments should have their dashboards"*
- **Resolves:** D7
- **Relates to:** doc 05 §10, doc 04 §3 and §6, doc 07 §6 (milestone list)

## Context

Doc 07's milestones build exactly two department surfaces: Marketing (M9) and
Operations (M11). Doc 05 §1 promises seven equal AI directors with a consistent
surface. Nothing in doc 07 says the other five are cut — they simply have no
milestone, which amounts to the same thing.

That gap was raised three times as D7 without an answer, because it is not a
question the documents can settle. Doc 07 wins on precedence, but precedence
resolves a *conflict*; it does not say what the product is meant to be.

The question was also framed badly the first two times, including by me. I
reported that Finance would ship "entirely locked" and Sales "nearly empty",
which was true of their *metric* widgets and wrong about the pages as a whole.
Doc 04 §3's truth table and doc 05's widget lists disagree with that summary.

## Decision

**All seven directors get a dashboard.** Each ships the widgets its available
data actually supports and renders the rest as named unlocks, per doc 04 §6
rule 1 — *"every locked tile states its unlock… the tile is a call to action,
not a failure."*

## What this actually costs, which is less than it appears

Six of the seven have real content with no integrations connected at all:

| Director | Day-one, website and documents only |
|---|---|
| Marketing | Growth Planner, Content Studio, SEO Intelligence, Brand audit, competitors |
| Sales | Lead Intelligence (doc 05 §4.5, *"works with no CRM connected"*), Proposal Studio (§4.7, same), outreach drafting |
| HR / People | Policy library and generator (§7.3, pure generation), JD generator, onboarding checklists, directory from the roster |
| Strategy | Market position (§8.1) from competitor data, crawl and SEO share |
| Operations | Everything, once the customer creates a first project — it is the first-party layer |
| Chief of Staff | Brain status (§2.8); Health Score once one department is scoreable; Baseline in week 1 |
| **Finance** | **Nothing** — every widget needs the accounting API |

So this is not five new products. It is five new pages, four of which are fed by
generation and crawl data that M2 and M7 already produce.

## Three things this decision does *not* change

**The composite score is still out of six, never seven.** Doc 05 §10 is explicit:
Chief of Staff and Strategy are synthesis layers and are never scored, and
Customers is scoreable but lives inside the Sales director rather than having a
page. Seven *pages* and six *scoreable departments* were always consistent —
task 9.3 stands unaltered.

**D6 is untouched.** Whether a Department Manager sees six directors or seven is
a question about who may open the Executive surface, not about which pages exist.
Doc 06 §2.4 restricts Chief of Staff, the Morning Brief and the composite score
to Owner and Executive; that remains open.

**No department page grants authority.** Opening the Finance dashboard grants
nothing — the caller's scope is resolved from role and membership, exactly as
before. A Contributor who opens Finance sees what a Contributor may see. This is
worth stating because seven pages make it far easier to assume otherwise.

## Finance is still open, and deliberately not defaulted

Every doc 05 §5 widget requires the accounting API that doc 07 §8 excludes.
Three options, recorded in D7:

1. Structure plus named unlocks — honest, but a dead page on day one.
2. Bring accounting into scope — makes Finance real, but adds an integration and
   a vendor decision, and doc 05 §10 already flags accounting as a single point
   of failure.
3. **Manual entry, visibly labelled self-reported** — which doc 04 §7 already
   sanctions (*"manual entry: ruled out → allowed at MVP"*) and doc 04 §6 rule 4
   already constrains (*"never silently mixed with API-sourced"*).

Recommended: (3) now, (2) when a design partner's accounting system is known.
The label carries real weight — a margin the owner typed is a different claim
from one fetched from an accounting API, and the product's entire position rests
on not blurring those two.

## Consequences

- **M9 grows** from "shell and Marketing" to the shell plus all seven director
  pages, each rendering what its data supports. The seven render states from
  doc 06 §7.1 do most of the work; without all seven, five of those pages have no
  honest way to display themselves.
- **M10 and M11 fill pages rather than create them.** Connecting a CRM turns
  Sales from its generation half to its pipeline half; the page already exists.
- **The assistant panel (task 9.1b) now matters more**, since it is the one
  surface consistent across all seven and the only useful thing on a page whose
  metrics are all locked.
- **Chief of Staff must handle "no scoreable department yet"** as a first-class
  state, not an error. In week 1 with nothing connected that is the normal case.
- Doc 07's milestone list no longer describes the build. That is expected — it is
  the contract for *how* to build, and this changes *what*. TASKS.md is the
  living record.

## Revisit if

A design partner's usage shows one of the generation-fed pages going unopened.
Four of these five exist because their content is cheap to produce, not because
demand for them is proven.
