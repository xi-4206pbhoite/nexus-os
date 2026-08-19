"""The seven directors and what each of their dashboards offers.

Doc 05 specifies every offering and, for each one, the sources it needs. ADR 0010
settles that all seven get a page rather than the two doc 07 schedules. This file
is that specification as **data**, for the same reason `ROLE_GRANTS` is data: a
capability-to-source map spread across React components cannot be audited, and
doc 04 §6 rule 1 — *"every locked tile states its unlock"* — is only true if the
unlock is stored next to the tile rather than written into a string by whoever
built the screen.

**Nothing here holds a value, and nothing here computes one.** An offering knows
its name, what it will show, and what it needs before it can show anything. The
numbers arrive in M8 and M9 through `calculators/`, which is pure and contains no
model (I1).

**`DELIVERED` is the honesty mechanism.** It lists the offering ids that have a
real implementation behind them. It is currently empty, so every tile renders as
`PLANNED` — *"not built yet"* — rather than as `LOCKED`, which would say
"connect Google Analytics and this works" about a widget that does not exist.
Those two states are both truthful and only one of them is true today; collapsing
them would make the page a promise instead of a placeholder. M9 adds ids to this
set, and the tiles change state without any other edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.scopes import Department


class Source(StrEnum):
    """What an offering needs before it can show anything.

    Taken from doc 05's *"Information assumptions"* column. Split finely enough
    that a gap banner can name one connection rather than "some data" — doc 05
    §1's banner is *"connect X to unlock 4 more capabilities here"*, which
    requires knowing which X.
    """

    CRAWL = "crawl"
    """The customer's own website, already fetched by Preview."""

    ONBOARDING = "onboarding"
    """Answers from the setup wizard — goals, budget, brand terms, currency."""

    DOCUMENTS = "documents"
    """Uploaded and indexed files (M5)."""

    ROSTER = "roster"
    """The people in the workspace, from membership."""

    LANGUAGE_MODEL = "language_model"
    """Generation. Unconfigured is a supported state (ADR 0011), so an offering
    that needs it renders unavailable rather than failing."""

    OPS_LAYER = "ops_layer"
    """NEXUS's own first-party records: projects, milestones, tasks, cost lines."""

    GA4 = "ga4"
    SEARCH_CONSOLE = "search_console"
    PAGESPEED = "pagespeed"
    DATAFORSEO = "dataforseo"
    CRM = "crm"
    ACCOUNTING = "accounting"
    ADS = "ads"
    ENRICHMENT = "enrichment"
    """Apollo / Clearbit. Phase 2."""

    TENDER_FEED = "tender_feed"
    """Doc 05 §2.5 and §12 — no provider is identified in any source document."""

    HISTORY = "history"
    """Enough elapsed periods to compare. Doc 04 §6 rule 3: week one is a
    baseline, not a brief."""


LABELS: dict[Source, str] = {
    Source.CRAWL: "your website",
    Source.ONBOARDING: "your setup answers",
    Source.DOCUMENTS: "uploaded documents",
    Source.ROSTER: "your team list",
    Source.LANGUAGE_MODEL: "a language model API key",
    Source.OPS_LAYER: "projects and tasks in NEXUS",
    Source.GA4: "Google Analytics",
    Source.SEARCH_CONSOLE: "Search Console",
    Source.PAGESPEED: "PageSpeed",
    Source.DATAFORSEO: "keyword data",
    Source.CRM: "your CRM",
    Source.ACCOUNTING: "your accounting system",
    Source.ADS: "an ad platform",
    Source.ENRICHMENT: "a contact enrichment provider",
    Source.TENDER_FEED: "a tender feed",
    Source.HISTORY: "a few weeks of history",
}


class WidgetState(StrEnum):
    """Doc 05 §0's four states, plus one this milestone needs.

    `PLANNED` is the addition, and it exists because the other four all describe
    a *built* widget. Rendering an unbuilt Growth Planner as `LOCKED` would tell
    the customer that answering some questions unlocks it, which is not true
    yet — and doc 04 §6 rule 1 makes the locked tile a call to action, so a
    false one is worse than no tile.
    """

    LIVE = "live"
    PARTIAL = "partial"
    LOCKED = "locked"
    WARMING = "warming"
    SELF_REPORTED = "self_reported"
    PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class Offering:
    """One widget on one director's page."""

    id: str
    """Doc 05's own numbering — `3.4` is the Growth Plan. Kept so a tile on the
    screen can be traced to the paragraph that specified it."""

    name: str
    shows: str
    needs: tuple[Source, ...]
    phase: int = 1
    """1 is MVP. Doc 05 marks some offerings Phase 2 or 3; they are listed so the
    page shows the shape of the product, and they are never presented as
    imminent."""

    note: str = ""
    """A constraint from doc 05 worth carrying to the screen — 'never estimated',
    'deterministic model in code; AI narrates only'."""


DELIVERED: frozenset[str] = frozenset()
"""Offering ids with a real implementation behind them.

Empty, deliberately. M9 is where this fills in, one offering at a time, and
until an id appears here its tile says it is not built. Anything else would put
a widget outline on the screen that a screenshot could not be distinguished from
a working one.
"""


@dataclass(frozen=True, slots=True)
class Director:
    department: Department
    title: str
    remit: str
    scoreable: bool
    """Doc 05 §10. Chief of Staff and Strategy are synthesis layers and are never
    scored — which is why the composite is out of six, not seven (ADR 0010)."""

    executive_only: bool
    """Doc 06 §2.4 — the Chief of Staff page, the Morning Brief and the composite
    score are Owner and Executive only. A Department Manager's portal is six
    directors, not seven, and that cost is acknowledged rather than hidden."""

    offerings: tuple[Offering, ...]


# ── The seven, from doc 05 sections 2 to 8 ────────────────────

CHIEF_OF_STAFF = Director(
    department=Department.EXECUTIVE,
    title="Nexus Chief of Staff",
    remit="Consumes every other department. Produces no data of its own.",
    scoreable=False,
    executive_only=True,
    offerings=(
        Offering(
            "2.1",
            "Morning Brief",
            "Six items and one recommended action, each citing its data",
            (Source.HISTORY, Source.LANGUAGE_MODEL),
            note=(
                "Week one shows a baseline instead — a brief is deltas, and in week one there is "
                "no prior week."
            ),
        ),
        Offering(
            "2.2",
            "Company Health Score",
            "Composite and per-department breakdown, with its denominator shown",
            (Source.HISTORY,),
            note="Scored against the six scoreable departments, never the seven directors.",
        ),
        Offering(
            "2.3",
            "Today's Priorities",
            "Ranked actions across departments",
            (Source.OPS_LAYER,),
        ),
        Offering(
            "2.4",
            "Risk Register",
            "Top risks with calculated financial exposure",
            (Source.ACCOUNTING, Source.CRM, Source.OPS_LAYER),
        ),
        Offering(
            "2.5",
            "Opportunity Radar",
            "Tenders, expansion signals, hiring activity",
            (Source.TENDER_FEED, Source.ENRICHMENT),
            phase=2,
            note=(
                "No tender provider is identified in any source document — an open procurement "
                "item."
            ),
        ),
        Offering(
            "2.6",
            "Decision Queue",
            "Decisions needing approval, with computed confidence",
            (Source.ADS,),
            phase=3,
            note="Confidence is computed in code, never by the model.",
        ),
        Offering(
            "2.7",
            "Department Briefings",
            "One status line per department, linking through",
            (),
        ),
        Offering(
            "2.8",
            "Company Brain status",
            "Facts known, their sources, and unconfirmed assumptions",
            (Source.ONBOARDING, Source.CRAWL, Source.DOCUMENTS),
        ),
        Offering(
            "2.9",
            "Board Pack export",
            "Assembled pack for a board or a bank",
            (Source.HISTORY,),
            phase=3,
        ),
    ),
)

MARKETING = Director(
    department=Department.MARKETING,
    title="AI Marketing Director",
    remit="The earliest department to become useful — on generation, before any integration.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering(
            "3.1",
            "Marketing score and drivers",
            "Score, delta, and what moved it",
            (Source.GA4,),
            note=(
                "Brand and SEO audit scores are separate and must not be merged into a Marketing "
                "score to manufacture a number."
            ),
        ),
        Offering(
            "3.2",
            "Traffic and conversion trend",
            "Sessions, users, sources, on-site conversion",
            (Source.GA4,),
            note="Lead-to-customer conversion is a different metric and also needs a CRM.",
        ),
        Offering(
            "3.3",
            "Channel performance",
            "Traffic by channel, and cost where available",
            (Source.GA4,),
            note=(
                "Cost columns have no connector at MVP — traffic only, with cost self-reported or "
                "locked."
            ),
        ),
        Offering(
            "3.4",
            "Growth Plan (90-day)",
            "Audience, positioning, channel mix, budget split, timeline",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
            note="The budget allocation must sum to the stated budget exactly.",
        ),
        Offering(
            "3.5",
            "Content and campaign calendar",
            "Scheduled and drafted items",
            (),
        ),
        Offering(
            "3.6",
            "Content Studio",
            "Blog, ad copy, email, captions, video scripts",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
            note=(
                "Depends on the prohibited and preferred terms, which cannot be inferred from a "
                "website."
            ),
        ),
        Offering(
            "3.7",
            "SEO Intelligence",
            "Keyword volumes and difficulty, gaps, briefs, technical issues",
            # Search Console was named in the note and missing from `needs`, which
            # meant it unlocked *nothing*: `offerings_needing` returned an empty
            # tuple for it, so a connection step would have offered a tool that
            # changes no tile, and this offering would have rendered Live with its
            # ranking half having no data source at all. Doc 05 §3.7 is explicit —
            # "Rankings need Search Console" — and §3 line 105 counts it among the
            # sources 3.7 requires. With it listed, connecting DataForSEO and the
            # crawl alone renders Partial, which is what "the ranking half" means.
            (Source.DATAFORSEO, Source.CRAWL, Source.SEARCH_CONSOLE),
            note="Volumes are fetched, never estimated. Rankings need Search Console.",
        ),
        Offering(
            "3.8",
            "Brand Intelligence",
            "Voice consistency, positioning, messaging gaps",
            (Source.CRAWL, Source.DOCUMENTS, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "3.9",
            "Competitor War Room",
            "Competitor ads, new pages, ranking moves, and what they mean",
            (Source.DATAFORSEO, Source.ADS),
            phase=2,
        ),
        Offering(
            "3.10",
            "Social publishing",
            "Queue, schedule, publish",
            (Source.ADS,),
            phase=2,
        ),
        Offering(
            "3.11",
            "Ad creative generation",
            "Generated image variants from brand assets",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
            phase=2,
        ),
        Offering(
            "3.12",
            "Landing page and CTA recommendations",
            "Prioritised on-page fixes",
            (Source.CRAWL, Source.GA4),
        ),
    ),
)

SALES = Director(
    department=Department.SALES,
    title="AI Sales Director",
    remit="Reads the customer's CRM. Owns no pipeline data.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering("4.1", "Sales score and drivers", "Score, delta, cause", (Source.CRM,)),
        Offering(
            "4.2",
            "Pipeline overview",
            "Value by stage, count, movement",
            (Source.CRM,),
            note="A missing CRM field disables the widget that needs it, not the whole page.",
        ),
        Offering(
            "4.3",
            "Forecast",
            "Weighted and committed forecast for the period",
            (Source.CRM, Source.HISTORY),
            note="Below three months of closed history: unweighted totals only, labelled as such.",
        ),
        Offering(
            "4.4",
            "Stale and at-risk deals",
            "Deals with no activity beyond a threshold",
            (Source.CRM,),
            note=(
                "Needs reliable activity timestamps — the field most often empty in real CRMs. "
                "Absent, this is disabled rather than guessed."
            ),
        ),
        Offering(
            "4.5",
            "Lead Intelligence",
            "Discovered prospects, match score, why this lead, suggested opener",
            (Source.ONBOARDING, Source.ENRICHMENT),
            phase=2,
            note="Works with no CRM connected.",
        ),
        Offering(
            "4.6",
            "Push to CRM",
            "Write discovered leads into their CRM",
            (Source.CRM,),
            phase=2,
            note="Needs write scope — a much heavier permission than read, asked for separately.",
        ),
        Offering(
            "4.7",
            "Proposal Studio",
            "Client-ready proposals, every price cited to a source document",
            (Source.DOCUMENTS, Source.LANGUAGE_MODEL),
            note=(
                "Works with no CRM connected. A superseded price list cited in a client proposal "
                "is the highest-damage failure in the product."
            ),
        ),
        Offering(
            "4.8",
            "Outreach drafting",
            "Email and message drafts in the company's voice",
            (Source.ONBOARDING, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "4.9",
            "Communication Intelligence",
            "Suggested communication style per contact",
            (Source.ENRICHMENT,),
            phase=2,
            note=(
                "Phrased as suggestion, never as fact about a person, and never used in hiring "
                "decisions."
            ),
        ),
        Offering(
            "4.10",
            "Win/loss analysis",
            "Patterns across won and lost deals",
            (Source.CRM, Source.HISTORY),
        ),
        Offering(
            "4.11",
            "Customer health and churn",
            "Health score, churn risk, revenue at risk",
            (Source.CRM, Source.ACCOUNTING, Source.HISTORY),
            phase=2,
        ),
        Offering(
            "4.12",
            "Deals-lite",
            "A minimal deal tracker for customers with no CRM",
            (Source.OPS_LAYER,),
            note=(
                "Explicitly not a CRM. Values entered here are self-reported and stay marked as "
                "such."
            ),
        ),
    ),
)

FINANCE = Director(
    department=Department.FINANCE,
    title="AI Finance Advisor",
    remit="Entirely gated on one connection.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering("5.1", "Finance score and drivers", "Score, delta", (Source.ACCOUNTING,)),
        Offering(
            "5.2",
            "Revenue trend",
            "By month, by service, by customer",
            (Source.ACCOUNTING,),
            note="CRM closed-won is a weaker proxy and is labelled with its source.",
        ),
        Offering(
            "5.3",
            "Margin analysis",
            "Gross and net margin, by service or project",
            (Source.ACCOUNTING, Source.OPS_LAYER),
        ),
        Offering(
            "5.4",
            "Cash position and runway",
            "Balance, burn, runway",
            (Source.ACCOUNTING, Source.HISTORY),
        ),
        Offering(
            "5.5",
            "Receivables ageing",
            "Overdue invoices, collection risk, chase drafts",
            (Source.ACCOUNTING,),
        ),
        Offering(
            "5.6",
            "Expenses against budget",
            "Category spend against plan",
            (Source.ACCOUNTING, Source.ONBOARDING),
            note="No API supplies a budget — it is entered, and stays marked as self-reported.",
        ),
        Offering(
            "5.7",
            "Pricing recommendations",
            "Where prices sit below market or below margin",
            (Source.DOCUMENTS, Source.ACCOUNTING),
        ),
        Offering("5.8", "Budget scenarios", "Compare planned allocations", (Source.ACCOUNTING,)),
        Offering(
            "5.9",
            "Business Simulator",
            "Price changes, hiring and expansion, modelled",
            (Source.ACCOUNTING, Source.OPS_LAYER),
            phase=3,
            note="Deterministic model in code; the model narrates only.",
        ),
        Offering(
            "5.10",
            "Can I afford X?",
            "Questions answered against real financials",
            (Source.ACCOUNTING, Source.LANGUAGE_MODEL),
            phase=3,
        ),
    ),
)

OPERATIONS = Director(
    department=Department.OPERATIONS,
    title="AI Operations Director",
    remit="The only system of record NEXUS owns. Everything here starts with your first project.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering("6.1", "Operations score and drivers", "Score, delta", (Source.OPS_LAYER,)),
        Offering(
            "6.2",
            "Active projects board",
            "Status, progress, on-time or at-risk",
            (Source.OPS_LAYER,),
        ),
        Offering("6.3", "Milestone timeline", "Milestones across projects", (Source.OPS_LAYER,)),
        Offering(
            "6.4", "Task queue and overdue", "Assigned work and overdue items", (Source.OPS_LAYER,)
        ),
        Offering(
            "6.5",
            "Capacity and utilisation",
            "Who is on what, and who is over-loaded",
            (Source.OPS_LAYER, Source.ROSTER),
            note=(
                "Available hours come from a settings assumption, not a measurement, and the ratio "
                "is labelled as part-assumption."
            ),
        ),
        Offering(
            "6.6",
            "Bottleneck analysis",
            "Where work consistently stalls",
            (Source.OPS_LAYER, Source.HISTORY),
        ),
        Offering(
            "6.7",
            "Project profitability",
            "Cost against contract value, per project",
            (Source.OPS_LAYER, Source.ACCOUNTING),
            note=(
                "The key cross-department interlock: the margin field renders Locked for anyone "
                "without Finance access."
            ),
        ),
        Offering(
            "6.8",
            "Delivery risk alerts",
            "Late milestones and the revenue they threaten",
            (Source.OPS_LAYER, Source.ACCOUNTING),
        ),
        Offering(
            "6.9",
            "Issue and snag register",
            "Open issues by severity and owner",
            (Source.OPS_LAYER,),
        ),
        Offering(
            "6.10",
            "Subcontractor performance",
            "On-time rate and issue rate per vendor",
            (Source.OPS_LAYER, Source.HISTORY),
        ),
        Offering(
            "6.11",
            "SOP library and builder",
            "Generated and stored procedures",
            (Source.LANGUAGE_MODEL,),
        ),
        Offering(
            "6.12",
            "Project document vault",
            "Per-project files, searchable",
            (Source.DOCUMENTS,),
        ),
    ),
)

PEOPLE = Director(
    department=Department.HR,
    title="AI HR Director",
    remit="Mostly generative — with one real data source once Operations is in use.",
    scoreable=True,
    executive_only=False,
    offerings=(
        Offering(
            "7.1", "Team directory and org view", "People, roles, reporting lines", (Source.ROSTER,)
        ),
        Offering(
            "7.2",
            "Capacity and utilisation",
            "Load per person",
            (Source.OPS_LAYER, Source.ROSTER),
            note=(
                "Assigned hours are measured; available hours are an assumption. The ratio is "
                "labelled as part-assumption."
            ),
        ),
        Offering(
            "7.3",
            "Policy library and generator",
            "HR policies in the company's voice",
            (Source.LANGUAGE_MODEL,),
            note=(
                "Labour law is country-specific — generated policies carry a review-by-local- "
                "counsel notice."
            ),
        ),
        Offering(
            "7.4",
            "Job descriptions and hiring plan",
            "Role descriptions and a hiring sequence",
            (Source.ROSTER, Source.ONBOARDING, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "7.5",
            "Onboarding checklists",
            "Per-role checklists, assignable as tasks",
            (Source.ROSTER, Source.LANGUAGE_MODEL),
        ),
        Offering(
            "7.6",
            "Training plans",
            "Skill gaps and outlines",
            (Source.ROSTER, Source.LANGUAGE_MODEL),
            note="Skill gaps are self-declared, not measured, and are labelled as such.",
        ),
    ),
)

STRATEGY = Director(
    department=Department.STRATEGY,
    title="AI Strategy Director",
    remit=(
        "A synthesis director. Reads the same computed objects as the Chief of Staff, so the two "
        "can never disagree."
    ),
    scoreable=False,
    executive_only=False,
    offerings=(
        Offering(
            "8.1",
            "Market position",
            "Where the company sits against its competitors",
            (Source.CRAWL, Source.DATAFORSEO),
        ),
        Offering(
            "8.2",
            "Service portfolio analysis",
            "Which services to grow, fix or drop",
            (Source.ACCOUNTING, Source.OPS_LAYER, Source.DATAFORSEO),
        ),
        Offering(
            "8.3",
            "Expansion analysis",
            "The case for a new market or service",
            (Source.DATAFORSEO, Source.ACCOUNTING),
        ),
        Offering(
            "8.4",
            "Scenario planning",
            "Compare strategic options",
            (Source.ACCOUNTING, Source.OPS_LAYER),
            phase=3,
            note="Shares the Simulator engine with Finance — deterministic in code.",
        ),
        Offering(
            "8.5",
            "Bid / no-bid advisor",
            "Whether to chase a tender, and at what price",
            (Source.TENDER_FEED, Source.CRM, Source.OPS_LAYER, Source.ACCOUNTING),
            phase=2,
            note="High value for contracting, and it needs three departments live.",
        ),
        Offering(
            "8.6",
            "Risk register",
            "Shared with the Chief of Staff",
            (Source.ACCOUNTING, Source.CRM, Source.OPS_LAYER),
        ),
    ),
)


DIRECTORS: tuple[Director, ...] = (
    CHIEF_OF_STAFF,
    MARKETING,
    SALES,
    FINANCE,
    OPERATIONS,
    PEOPLE,
    STRATEGY,
)

BY_DEPARTMENT: dict[Department, Director] = {d.department: d for d in DIRECTORS}


# ── State ─────────────────────────────────────────────────────


def state_for(offering: Offering, *, connected: frozenset[Source]) -> WidgetState:
    """What this offering renders as, given what the workspace actually has.

    Order matters. `PLANNED` is checked first because an unbuilt widget cannot be
    unlocked by connecting anything, and telling someone otherwise is a promise
    the product would then break. Only once an offering is delivered does the
    question "what is missing?" have a useful answer.
    """
    if offering.id not in DELIVERED:
        return WidgetState.PLANNED

    missing = [source for source in offering.needs if source not in connected]
    if not missing:
        return WidgetState.LIVE
    if len(missing) == len(offering.needs):
        return WidgetState.LOCKED
    # Some inputs present, so there is something real to show at reduced scope.
    return WidgetState.PARTIAL


CONNECTABLE: tuple[Source, ...] = (
    Source.GA4,
    Source.SEARCH_CONSOLE,
    Source.CRM,
    Source.ACCOUNTING,
    Source.ADS,
)
"""The sources a *customer* connects, and nothing else.

`Source` is deliberately wider than this, and the exclusions are the point — a
connection step that offered all sixteen would be asking people to connect things
that are not theirs to connect:

- **CRAWL** happens on its own, from the URL they already gave.
- **ONBOARDING** is the wizard they are standing in.
- **ROSTER** is the team step, and comes from `membership`.
- **OPS_LAYER** is NEXUS's own first-party records. There is nothing external to
  attach; it fills up by being used (M11).
- **HISTORY** is time passing. Offering to connect it would be absurd, and doc 04
  §6 rule 3 is explicit that week one is a baseline rather than a brief.
- **PAGESPEED**, **DATAFORSEO**, **ENRICHMENT**, **TENDER_FEED** are *our* provider
  accounts, not the customer's — and two of them are unresolved procurement
  (**D2** keyword data, and doc 05 §2.5's note that no tender provider is named in
  any source document). Listing them here would ask a customer to solve our
  supplier problem.
- **LANGUAGE_MODEL** is an API key set by whoever runs the deployment (ADR 0011),
  not a per-workspace connection.

What remains is the five M10 was scoped around, plus Ads. None of them is
implemented — **D3** (Google credentials) and **D10** (which CRM) are both open —
so this list drives an honest "not connected" surface and nothing more.
"""


def offerings_needing(source: Source) -> tuple[Offering, ...]:
    """Every capability that would become reachable if this were connected.

    Built from the same offering definitions the dashboards render, so the count a
    connection step shows and the tiles a director page locks cannot disagree. The
    alternative — a hand-written "connect GA4 to unlock 6 things" — is a number that
    goes stale the first time doc 05's spec changes.
    """
    return tuple(
        offering
        for director in DIRECTORS
        for offering in director.offerings
        if source in offering.needs
    )


def missing_sources(offering: Offering, *, connected: frozenset[Source]) -> tuple[Source, ...]:
    """What is not yet in place. Doc 04 §6 rule 1 — the tile states its unlock."""
    return tuple(source for source in offering.needs if source not in connected)


def unlock_sentence(offering: Offering, *, connected: frozenset[Source]) -> str:
    """The unlock, in words, or an empty string when there is nothing missing.

    Built here rather than in the UI so that one wording change reaches every
    surface, and so a tile can never be shipped with the outline drawn and the
    sentence forgotten.
    """
    missing = missing_sources(offering, connected=connected)
    if not missing:
        return ""
    names = [LABELS[source] for source in missing]
    if len(names) == 1:
        return f"Needs {names[0]}."
    return f"Needs {', '.join(names[:-1])} and {names[-1]}."


def landing_department(
    *, executive_surface: bool, departments: frozenset[Department]
) -> Department | None:
    """Which director to open after signing in.

    Resolved from the caller's **membership**, never from the `department`
    answer in onboarding. That answer is a stated fact about the person; the
    membership is what authorises, and landing someone on a page their scope
    does not reach would produce a 404 immediately after setup.

    Owner and Executive land on the Chief of Staff, which is the only page that
    reads across all seven. Everyone else lands on their own department, and a
    caller with no department at all gets `None` — there is no sensible default,
    and picking one would put someone in a department nobody assigned them to.
    """
    if executive_surface:
        return Department.EXECUTIVE
    if not departments:
        return None
    return sorted(departments)[0]
