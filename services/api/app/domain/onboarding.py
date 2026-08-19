"""The onboarding question catalogue, with a scope on every answer.

Doc 06 §2.5: *"Onboarding answers carry scope like anything else. Average deal
size and marketing budget are L3 Sales and L3 Finance facts. They are not
'company facts' visible to everyone merely because they arrived through a
form. Tag them at capture."*

That last clause is why this is a catalogue rather than a form handler. A scope
applied later is a scope someone can forget to apply; here every question
carries its classification as data, and a test asserts that none is missing and
that the sensitive ones are not L1.

The ordering matters too. Doc 06 §4.10 requires the brief-recipients question to
come **after** team invitation, because recipients must be workspace users — you
cannot pick them from a list that does not exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.dashboards import CONNECTABLE
from app.domain.scopes import Department, Role, Scope


class Pass(StrEnum):
    """Doc 06 §2.5 — two passes, separated by the audit.

    Pass 1 is what is needed to run the audit. Pass 2 is asked *after* the user
    has seen something real about their own business, which is the only moment
    that earns the right to ask for the rest (doc 04 §5).
    """

    ONE = "pass_1"
    TWO = "pass_2"
    # Doc 08 §2-§7. Only the departments the company says it runs, and only the
    # ones this caller may reach — see `Question.asked_of`.
    DEPARTMENT = "department"
    # Doc 04 §5 stage 4. Nothing is connected by answering: no connector exists
    # (M10), so this records which tools the customer *has*, and the dashboards go
    # on saying Locked until one is actually wired up.
    CONNECT = "connect"
    # After team invitation, per doc 06 §4.10.
    POST_INVITE = "post_invite"


class AnswerType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    RANKED = "ranked"
    MONEY = "money"
    URL = "url"
    USER_LIST = "user_list"


@dataclass(frozen=True, slots=True)
class Choice:
    """One option on a closed-set question."""

    value: str
    label: str


def _choices(source: type[StrEnum], labels: dict[str, str] | None = None) -> tuple[Choice, ...]:
    """Options taken from an enum, so the two cannot drift apart.

    `role` and `department` are asked as questions *and* are the vocabulary of
    the security model. Typing their options out a second time here would create
    a copy that a later change to `scopes.py` would silently leave stale.
    """
    overrides = labels or {}
    return tuple(
        Choice(m.value, overrides.get(m.value, m.value.replace("_", " ").title())) for m in source
    )


# Closed sets only. A question whose answers are the customer's own words —
# their goals, their challenges, the terms they will not use — carries no
# options and is entered freely; offering a menu there would put our vocabulary
# in their mouth and then store the result as their stated intent.
CURRENCIES: tuple[Choice, ...] = tuple(
    Choice(code, f"{code} — {name}")
    for code, name in (
        # OMR was missing, in a product whose market is Oman and whose sign-up form
        # placeholder is `you@yourcompany.om`. Doc 08 §1.3 lists it first and doc 01
        # §3's regional principle names "OMR/AED/SAR"; the list had the other two.
        # Found by trying to complete setup as an Omani company and being told the
        # rial "is not an option".
        #
        # It sorts first deliberately rather than alphabetically: this is the default
        # a majority of customers want, and a select whose most likely answer is
        # eleventh is a select that gets mis-answered.
        ("OMR", "Omani rial"),
        ("AED", "UAE dirham"),
        ("AUD", "Australian dollar"),
        ("CAD", "Canadian dollar"),
        ("CHF", "Swiss franc"),
        ("EUR", "Euro"),
        ("GBP", "Pound sterling"),
        ("INR", "Indian rupee"),
        ("JPY", "Japanese yen"),
        ("SAR", "Saudi riyal"),
        ("SGD", "Singapore dollar"),
        ("USD", "US dollar"),
        ("ZAR", "South African rand"),
    )
)

MONTHS: tuple[Choice, ...] = tuple(
    Choice(str(number), name)
    for number, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
)


class Sink(StrEnum):
    """Where an answer actually lands.

    Almost everything is an `onboarding_answer` row, and that table is unique on
    `(workspace_id, question_key)` — a *workspace* fact. Two of the things the
    registration flow has to collect are not:

    - **The person's own name** is per user. As an answer, two members of one
      workspace would fight over a single row, and the second would silently
      overwrite the first.
    - **The company's name** already exists, as `workspace.name`. Writing it to
      `onboarding_answer` as well would give one fact two homes that can disagree,
      which is precisely the drift that produced `ReviewState`'s wrong spelling and
      a `document.status` of `indexed` that nothing had earned.

    So those two write through to their real column instead. The alternative —
    special-casing them in the route — would put the routing rule somewhere no
    question can be read next to, and this catalogue is meant to be the one place
    a question's behaviour is legible.
    """

    ANSWER = "answer"
    """An `onboarding_answer` row, classified from the catalogue. The default."""

    WORKSPACE_NAME = "workspace_name"
    """`workspace.name`. The company's name has exactly one home."""

    USER_DISPLAY_NAME = "user_display_name"
    """`app_user.display_name`, for the calling user and nobody else.

    Written with `WHERE id = <session's user id>`, never an id from the request —
    the caller's identity is bound to the session (I2), so there is no argument
    here to get wrong.
    """


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    prompt: str
    stage: Pass
    answer_type: AnswerType
    scope: Scope
    department: Department | None
    """The department that owns this fact at L3. `None` for L1/L2 facts."""
    asked_of: Department | None = None
    """Whose question block this belongs to. `None` means company-wide.

    **Deliberately not the same field as `department`, and D15 is explicit about
    why.** They answer different questions and routinely disagree:

    - `department` is a *classification* — which department owns the answer as an
      L3 fact. It is what the scope predicate filters on.
    - `asked_of` is *routing* — which department's block the question appears in,
      and therefore who is asked it at all.

    Doc 08 §4.3 ("above what amount does spend need approval?") is asked of Finance
    **and** classified L3 Finance, so both are set and they agree. Doc 08 §3.1 ("what
    are your pipeline stages?") is asked of Sales and classified L2 — structural, not
    sensitive — so `asked_of` is Sales and `department` is None. Collapsing the two
    would have made every Sales question an L3 Sales fact, which would hide the
    pipeline stages from a Viewer for no reason, and would have made every L3 fact
    into a routing rule.
    """
    required: bool = False
    why: str = ""
    """Shown to the user. Doc 04 §5 — every question should be justified by
    something they have already seen."""
    sink: Sink = Sink.ANSWER
    """Where the value is stored. See `Sink` — the default is the ordinary case."""
    options: tuple[Choice, ...] = ()
    """The permitted answers, when the set is genuinely closed.

    Empty means free entry, and `USER_LIST` is a third case: its options are the
    workspace's current members, which are not knowable here — doc 06 §4.10 is
    the reason, and resolving them per workspace is the route's job.
    """

    @property
    def free_entry(self) -> bool:
        return not self.options and self.answer_type is not AnswerType.USER_LIST


TOOL_LABELS: dict[str, str] = {
    "ga4": "Google Analytics",
    "search_console": "Google Search Console",
    "crm": "A CRM",
    "accounting": "An accounting system",
    "ads": "An ad platform",
}
"""Names for the connection step, written out rather than derived.

`dashboards.LABELS` exists for a different job: it fills the middle of a sentence
("Needs **your CRM**."), so its entries are lower-case fragments with possessives.
Transforming them into standalone option labels produced "Crm" and "An ad platform"
as a heading — worse than either source. The keys are checked against `CONNECTABLE`
below, so the two lists still cannot drift apart.
"""

CONNECTABLE_TOOLS: tuple[Choice, ...] = tuple(
    Choice(source.value, TOOL_LABELS[source.value]) for source in CONNECTABLE
)
"""What a customer may be asked about. Ordered as `CONNECTABLE` is.

A `KeyError` here at import time is the intended failure: adding a source to
`CONNECTABLE` without naming it should stop the application starting rather than
render a blank option.
"""


SCOREABLE_DEPARTMENTS: tuple[Choice, ...] = (
    Choice(Department.MARKETING.value, "Marketing"),
    Choice(Department.SALES.value, "Sales"),
    Choice(Department.FINANCE.value, "Finance"),
    Choice(Department.OPERATIONS.value, "Operations"),
    Choice(Department.HR.value, "People / HR"),
    Choice(Department.STRATEGY.value, "Strategy"),
)
"""The six a company can be asked about.

`Department.EXECUTIVE` is deliberately absent. It is a synthesis layer that
consumes the others and produces no data of its own, which is why the composite
score is out of six and never seven (doc 05 §10, `ARCHITECTURE.md` §7) — and why
doc 08 documents six question blocks.

Doc 08 §1.6 says "multi-select across the **seven** below" and computes 39 fields
from `4 + 7 x 5`. Only six blocks exist in that document, and the seventh would have
to be Executive, which by doc 05's own rule has nothing to ask. Read as six: 34
fields, not 39. Recorded in ADR 0015 rather than silently reconciled.
"""


def _dept(
    key: str,
    prompt: str,
    asked_of: Department,
    answer_type: AnswerType,
    why: str,
    *,
    scope: Scope = Scope.L2_COMPANY_INTERNAL,
    department: Department | None = None,
    options: tuple[Choice, ...] = (),
) -> Question:
    """One question in a department block.

    `scope` defaults to L2 because most of these are *definitions* — what counts as
    a lead, when an order is late, which stages the pipeline has. Doc 08 §0 says the
    whole set is L1 or L2, and for most of it that is right.

    Where it is not right, `scope` and `department` are set explicitly. Doc 06 §2.5
    outranks doc 08 here and is unambiguous: *"Average deal size and marketing budget
    are L3 Sales and L3 Finance facts. They are not 'company facts' visible to
    everyone merely because they arrived through a form."* A spend-approval threshold
    and a runway figure are the same kind of fact, so they are classified the same way
    rather than published to every Viewer because a form collected them.
    """
    return Question(
        key=key,
        prompt=prompt,
        stage=Pass.DEPARTMENT,
        answer_type=answer_type,
        scope=scope,
        department=department,
        why=why,
        asked_of=asked_of,
        options=options,
    )


def _opts(*pairs: tuple[str, str]) -> tuple[Choice, ...]:
    return tuple(Choice(value, label) for value, label in pairs)


_M, _S, _F, _O, _P, _St = (
    Department.MARKETING,
    Department.SALES,
    Department.FINANCE,
    Department.OPERATIONS,
    Department.HR,
    Department.STRATEGY,
)

DEPARTMENT_QUESTIONS: tuple[Question, ...] = (
    # 28, where doc 08 §2-§7 lists 30. The two missing ones already exist in the
    # company-wide passes and are **reused rather than asked twice**:
    #
    #   §2.3 "Monthly budget for acquisition" -> `monthly_marketing_budget` (L3 Finance)
    #   §4.1 "When does your financial year end?" -> `fiscal_year_start`
    #
    # Asking either again would put one fact in two rows and let them disagree, which
    # is the same reasoning `Sink` exists for.
    #
    # ── Marketing (doc 08 §2A) ────────────────────────────────
    _dept(
        "lead_definition",
        "What counts as a lead worth passing to Sales?",
        _M,
        AnswerType.LONG_TEXT,
        "The denominator of every conversion figure. Without it, conversion rate has "
        "no agreed meaning.",
    ),
    _dept(
        "channels_run",
        "Which channels do you actively run?",
        _M,
        AnswerType.MULTI_CHOICE,
        "A channel you do not run is reported as not run, never as zero.",
        options=_opts(
            ("search", "Search"),
            ("paid", "Paid advertising"),
            ("social", "Social"),
            ("referrals", "Referrals"),
            ("trade_shows", "Trade shows"),
            ("email", "Email"),
        ),
    ),
    _dept(
        "lost_to",
        "Who do you most often lose to?",
        _M,
        AnswerType.TEXT,
        "Seeds competitor tracking before discovery has run.",
    ),
    _dept(
        "arabic_content",
        "Is Arabic-language content in scope this year?",
        _M,
        AnswerType.SINGLE_CHOICE,
        "Decides whether the Arabic-language gap is an opportunity or out of scope.",
        options=_opts(
            ("not_yet", "Not yet"), ("planned", "Planned"), ("publishing", "Already publishing")
        ),
    ),
    # ── Sales (doc 08 §3A) ────────────────────────────────────
    _dept(
        "pipeline_stages",
        "What are your pipeline stages, in order?",
        _S,
        AnswerType.TEXT,
        "The board columns, and the stage conversion rates a forecast is built from.",
    ),
    _dept(
        "stale_deal_days",
        "After how many days of silence should a deal be flagged?",
        _S,
        AnswerType.SINGLE_CHOICE,
        "The stale-deal threshold. 'Use my median cycle' derives it from your own "
        "history rather than a generic 30-day rule.",
        options=_opts(
            ("7", "7 days"),
            ("10", "10 days"),
            ("14", "14 days"),
            ("median_cycle", "Use my median cycle"),
        ),
    ),
    _dept(
        "lead_assignment",
        "How are new leads assigned?",
        _S,
        AnswerType.SINGLE_CHOICE,
        "Decides whether an unassigned lead is an error state or normal.",
        options=_opts(
            ("round_robin", "Round robin"),
            ("by_region", "By region"),
            ("by_product", "By product"),
            ("manager", "Manager assigns"),
        ),
    ),
    _dept(
        "quota_period",
        "What is the quota period?",
        _S,
        AnswerType.SINGLE_CHOICE,
        "The attainment window. 'No formal quota' suppresses attainment entirely "
        "rather than inventing a target.",
        options=_opts(
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("annual", "Annual"),
            ("none", "No formal quota"),
        ),
    ),
    _dept(
        "deal_disqualifiers",
        "What disqualifies a deal outright?",
        _S,
        AnswerType.LONG_TEXT,
        "Which deals are excluded from the forecast rather than weighted low.",
    ),
    # ── Finance (doc 08 §4A) ──────────────────────────────────
    _dept(
        "payment_terms",
        "Standard payment terms you offer?",
        _F,
        AnswerType.SINGLE_CHOICE,
        "The ageing buckets, and what counts as overdue.",
        options=_opts(
            ("on_receipt", "On receipt"),
            ("30", "30 days"),
            ("45", "45 days"),
            ("60", "60 days"),
        ),
    ),
    _dept(
        "spend_approval_threshold",
        "Above what amount does spend need approval?",
        _F,
        AnswerType.MONEY,
        "Which requests enter the approvals queue at all.",
        # L3 Finance, not L2. Doc 06 §2.5's rule: a money threshold is not a company
        # fact visible to every Viewer because a form collected it.
        scope=Scope.L3_DEPARTMENT,
        department=Department.FINANCE,
    ),
    _dept(
        "spend_approver",
        "Who approves spend above that?",
        _F,
        AnswerType.SINGLE_CHOICE,
        "Where an approval routes.",
        options=_opts(
            ("owner", "Owner only"),
            ("owner_or_finance", "Owner or Finance Manager"),
            ("department_manager", "Department manager"),
            ("board", "Board"),
        ),
    ),
    _dept(
        "runway_alert_months",
        "How many months of runway would worry you?",
        _F,
        AnswerType.SINGLE_CHOICE,
        "The runway alert threshold - a judgement of yours, never a benchmark of ours.",
        # L3 Finance: the answer discloses how close to the edge the company is.
        scope=Scope.L3_DEPARTMENT,
        department=Department.FINANCE,
        options=_opts(("3", "Under 3"), ("6", "Under 6"), ("9", "Under 9"), ("12", "Under 12")),
    ),
    # ── Operations (doc 08 §5A) ───────────────────────────────
    _dept(
        "promised_lead_time",
        "What do you promise customers as a lead time?",
        _O,
        AnswerType.TEXT,
        "The baseline on-time dispatch is measured against.",
    ),
    _dept(
        "usual_delay_cause",
        "What usually causes a delay?",
        _O,
        AnswerType.SINGLE_CHOICE,
        "Which bottleneck is checked first when dispatch slips.",
        options=_opts(
            ("stock_outs", "Stock-outs"),
            ("supplier_lead_time", "Supplier lead time"),
            ("picking_capacity", "Picking capacity"),
            ("transport", "Transport"),
        ),
    ),
    _dept(
        "stock_model",
        "Do you hold stock, or order per job?",
        _O,
        AnswerType.SINGLE_CHOICE,
        "Whether stock levels and reorder minimums apply at all.",
        options=_opts(("hold_stock", "Hold stock"), ("per_job", "Order per job"), ("both", "Both")),
    ),
    _dept(
        "order_late_definition",
        "At what point is an order officially late?",
        _O,
        AnswerType.SINGLE_CHOICE,
        "The definition of late, and therefore the on-time percentage.",
        options=_opts(
            ("missed_date", "Missed promised date"),
            ("one_day", "One day after"),
            ("three_days", "Three days after"),
        ),
    ),
    _dept(
        "supplier_concentration",
        "Which supplier are you most exposed to?",
        _O,
        AnswerType.LONG_TEXT,
        "Concentration risk, before purchase history is long enough to show it.",
        # L3 Operations: a named dependency and its share is commercially sensitive,
        # and the example answer in doc 08 is exactly that.
        scope=Scope.L3_DEPARTMENT,
        department=Department.OPERATIONS,
    ),
    # ── People (doc 08 §6A) ───────────────────────────────────
    _dept(
        "leave_model",
        "Is leave accrued monthly or granted annually?",
        _P,
        AnswerType.SINGLE_CHOICE,
        "How the leave liability is computed - a different formula, not a different label.",
        options=_opts(
            ("accrued", "Accrued monthly"),
            ("granted", "Granted annually"),
            ("mixed", "Mixed by contract"),
        ),
    ),
    _dept(
        "hire_approver",
        "Who signs off a new hire?",
        _P,
        AnswerType.SINGLE_CHOICE,
        "Where a requisition routes.",
        options=_opts(
            ("owner", "Owner only"),
            ("owner_and_manager", "Owner and department manager"),
            ("department_manager", "Department manager"),
        ),
    ),
    _dept(
        "people_risk",
        "What is your biggest people risk right now?",
        _P,
        AnswerType.LONG_TEXT,
        "Links a vacancy to the operational impact it is having.",
        # L3 HR. Doc 08's own example names an individual's role and the gap they
        # leave; a free-text people risk will often identify a person.
        scope=Scope.L3_DEPARTMENT,
        department=Department.HR,
    ),
    _dept(
        "review_cycle",
        "Do you run performance reviews on a cycle?",
        _P,
        AnswerType.SINGLE_CHOICE,
        "Whether review timing appears at all.",
        options=_opts(
            ("none", "No formal cycle"),
            ("annual", "Annual"),
            ("twice", "Twice a year"),
            ("quarterly", "Quarterly"),
        ),
    ),
    _dept(
        "track_document_expiry",
        "Should NEXUS track visa and document expiry?",
        _P,
        AnswerType.SINGLE_CHOICE,
        "A GCC-specific capability, opt-in because it involves sensitive documents.",
        options=_opts(("yes", "Yes"), ("no", "No"), ("not_yet", "Not yet")),
    ),
    # ── Strategy (doc 08 §7A) ─────────────────────────────────
    _dept(
        "twelve_month_success",
        "What would make the next twelve months a success?",
        _St,
        AnswerType.LONG_TEXT,
        "What every opportunity is ranked against.",
    ),
    _dept(
        "competitors_to_watch",
        "Which competitors should NEXUS watch?",
        _St,
        AnswerType.TEXT,
        "Seeds the tracked set before discovery runs.",
    ),
    _dept(
        "target_market",
        "Which market or segment are you trying to enter?",
        _St,
        AnswerType.TEXT,
        "Whether a regional signal is an opportunity or noise.",
        # L3 Strategy: unannounced expansion intent.
        scope=Scope.L3_DEPARTMENT,
        department=Department.STRATEGY,
    ),
    _dept(
        "binding_constraint",
        "What is the binding constraint today?",
        _St,
        AnswerType.SINGLE_CHOICE,
        "Which recommendations are suppressed as unactionable.",
        options=_opts(
            ("cash", "Cash"),
            ("people", "People"),
            ("stock", "Stock"),
            ("demand", "Demand"),
            ("time", "Time"),
        ),
    ),
    _dept(
        "deliberately_not_doing",
        "What are you deliberately not doing?",
        _St,
        AnswerType.LONG_TEXT,
        "Stops NEXUS recommending something you have already ruled out.",
    ),
)


CATALOGUE: tuple[Question, ...] = (
    # ── Pass 1: enough to run the audit ───────────────────────
    #
    # **Four questions, and one of them required.** Pass 1 is the whole of signup,
    # so its size is the thing that decides whether anybody finishes. It is held to
    # one test: could the audit run without this answer? If yes, the question waits.
    #
    # Two identity questions are here despite failing that test, because neither
    # costs the user any thought and both are needed before the product can address
    # them at all: registration names the workspace from the email domain, so
    # without them the company is called `acmetrading.om` on every screen and the
    # assistant writes to an email address.
    #
    # `role` and `department` used to be here, and required. They moved to Pass 2 —
    # see the note on `role` for why asking them at the door was both unnecessary
    # and slightly dishonest.
    Question(
        key="your_name",
        prompt="What should we call you?",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        # About the person, visible to their colleagues. Never L1: a name is not
        # published material just because a company's services are.
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="So the brief and the assistant address you rather than your email address.",
        sink=Sink.USER_DISPLAY_NAME,
    ),
    Question(
        key="company_name",
        prompt="Your company's name",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        # A company's own name is published material by definition.
        scope=Scope.L1_COMPANY_PUBLIC,
        department=None,
        why=(
            "Registration named your workspace from your email domain. This replaces "
            "it, and appears on anything you generate."
        ),
        sink=Sink.WORKSPACE_NAME,
    ),
    Question(
        key="company_url",
        prompt="Your website address",
        stage=Pass.ONE,
        answer_type=AnswerType.URL,
        # Published material. Genuinely public.
        scope=Scope.L1_COMPANY_PUBLIC,
        department=None,
        required=True,
        why="We read it to build your first audit.",
    ),
    Question(
        key="stated_purpose",
        prompt="What do you want help with most?",
        stage=Pass.ONE,
        # Doc 08 §1.5, and a closed set rather than the free text this was.
        #
        # The change matters because the answer *does* something: each value maps to
        # a landing screen in `agents/persona.PURPOSE_LANDING`, by a pure function
        # rather than by a model reading prose and guessing. Free text could not
        # drive that without something inferring intent from a sentence, which is
        # exactly the kind of quiet judgement doc 08 §1.5 replaces with four options.
        #
        # Converted under ADR 0015, which makes doc 08 authoritative for question
        # content. Answers stored as free text before this simply do not match an
        # option and render unselected — visible, and correctable by answering again.
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="It decides what each dashboard leads with. It changes emphasis, never access.",
        options=(
            Choice("diagnose", "Find out what is quietly broken"),
            Choice("consolidate", "Get one place for the numbers"),
            Choice("time", "Free up my own time"),
            Choice("grow", "Prepare for growth or funding"),
        ),
    ),
    # ── Pass 2: after the audit ───────────────────────────────
    #
    # These two are **stated facts, not grants**. Answering them writes a row in
    # `onboarding_answer`; it never touches `membership`, which is the only thing
    # `build_scope` reads and therefore the only thing that authorises anything.
    # Doc 06 §2.2 — a self-declared role is privilege escalation via dropdown, so
    # the escalation has to be impossible rather than merely unimplemented.
    #
    # **Moved out of Pass 1, and no longer required.** Two reasons, and the second is
    # the stronger one:
    #
    #   1. The audit does not read either of them, so by Pass 1's own test they do
    #      not belong there. They shape emphasis — which dashboard leads with what —
    #      and emphasis can be set after something has been shown.
    #   2. The person answering these during signup is, without exception, the Owner
    #      who just cleared the domain gate. Their real role and department are
    #      already in `membership`, which is the only record that decides anything.
    #      Asking them to type it anyway made the form open with two dropdowns whose
    #      answer the product already held, next to help text explaining that the
    #      answer does not do what a reader would assume it does. A question that has
    #      to disclaim its own effect is a question worth deferring.
    #
    # They stay in the catalogue, answerable, because they are genuinely useful for a
    # *later* member whose stated role differs from the membership they were given.
    Question(
        key="role",
        prompt="What is your role?",
        stage=Pass.TWO,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why=(
            "It shapes what your assistant leads with. It does not change what you "
            "can see — that comes from your membership, not from this answer."
        ),
        options=_choices(Role, {"external": "External / Client"}),
    ),
    Question(
        key="department",
        prompt="Which department is that in?",
        stage=Pass.TWO,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        # Doc 06 §2.3 — derived from role, confirmable, Owner-overridable.
        why="Derived from your role. Correct it if it is wrong.",
        options=_choices(Department, {"hr": "HR / People"}),
    ),
    Question(
        key="ranked_goals",
        prompt="Rank your goals for this quarter",
        stage=Pass.TWO,
        answer_type=AnswerType.RANKED,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="Intent is not published anywhere — we cannot infer it from your site.",
    ),
    Question(
        key="biggest_challenges",
        prompt="What is getting in the way?",
        stage=Pass.TWO,
        answer_type=AnswerType.MULTI_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="It orders the improvement roadmap.",
    ),
    # Doc 08 §1.1. In Pass 2 deliberately: the whole justification for asking is
    # that the crawl has already guessed a category and guessed it imprecisely, so
    # the question only earns its place *after* the audit has run.
    Question(
        key="what_we_sell",
        prompt="What does the business sell?",
        stage=Pass.TWO,
        answer_type=AnswerType.TEXT,
        scope=Scope.L1_COMPANY_PUBLIC,
        department=None,
        why=(
            "The crawl infers a category imprecisely. Your own words anchor every "
            "generated artefact, competitor match and opportunity."
        ),
    ),
    Question(
        key="ideal_customer",
        prompt="Describe your ideal customer, in your words",
        stage=Pass.TWO,
        answer_type=AnswerType.LONG_TEXT,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="Often different from who you currently serve.",
    ),
    # Doc 08 §1.4, with its option bands verbatim. A band rather than a number
    # because nobody knows their headcount exactly and a spurious integer would be
    # treated as a measurement.
    Question(
        key="headcount",
        prompt="Roughly how many people?",
        stage=Pass.TWO,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="Sizes the People department, and decides which benchmarks apply.",
        options=(
            Choice("under_10", "Under 10"),
            Choice("10_to_50", "10-50"),
            Choice("50_to_200", "50-200"),
            Choice("over_200", "Over 200"),
        ),
    ),
    Question(
        key="average_deal_size",
        prompt="What is your average deal size?",
        stage=Pass.TWO,
        answer_type=AnswerType.MONEY,
        # Doc 06 §2.5, named explicitly. Not a company fact.
        scope=Scope.L3_DEPARTMENT,
        department=Department.SALES,
        why="Used for pipeline value and forecasting.",
    ),
    Question(
        key="monthly_marketing_budget",
        prompt="What is your monthly marketing budget?",
        stage=Pass.TWO,
        answer_type=AnswerType.MONEY,
        # Doc 06 §2.5, named explicitly.
        scope=Scope.L3_DEPARTMENT,
        department=Department.FINANCE,
        why="The growth plan allocates against it, and must sum to it exactly.",
    ),
    Question(
        key="forbidden_terms",
        prompt="Words we should never use",
        stage=Pass.TWO,
        answer_type=AnswerType.MULTI_CHOICE,
        # Brand voice is published material in effect — every generated line
        # carries it outward.
        scope=Scope.L1_COMPANY_PUBLIC,
        department=None,
        why="Tone can be inferred from your site; prohibitions cannot.",
    ),
    Question(
        key="preferred_terms",
        prompt="Words we should use",
        stage=Pass.TWO,
        answer_type=AnswerType.MULTI_CHOICE,
        scope=Scope.L1_COMPANY_PUBLIC,
        department=None,
        why="Your own vocabulary, so generated copy sounds like you rather than like us.",
    ),
    Question(
        key="currency",
        prompt="Which currency do you report in?",
        stage=Pass.TWO,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        # No longer required to finish setup. It is required to render a *figure*,
        # which is a different moment: the surfaces that show money are M6 onward and
        # none of them exists yet, so blocking completion on it bought nothing and
        # cost a mandatory select with thirteen options. Whatever first needs to
        # format an amount asks then, when the question explains itself.
        why="Every figure in the product is shown in it.",
        options=CURRENCIES,
    ),
    Question(
        key="fiscal_year_start",
        prompt="When does your financial year start?",
        stage=Pass.TWO,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        # Same argument as `currency`: it is a precondition for a period comparison,
        # not for having an account. January is the overwhelming default and guessing
        # it silently would be the wrong fix, so it is asked — just not at the door.
        why="Period comparisons depend on it.",
        options=MONTHS,
    ),
    # Doc 08 §1.6. Which blocks the company is asked at all, so it has to be
    # answered before the department stage can render anything.
    Question(
        key="departments_run",
        prompt="Which of these does your company actually run?",
        stage=Pass.TWO,
        answer_type=AnswerType.MULTI_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        # **Not required, and that is the single largest cut in this file.** Requiring
        # it made signup's length depend on an answer given inside signup: ticking all
        # six added 28 further questions, and the user had no way to see that cost
        # before paying it. Nothing downstream breaks when it is unanswered —
        # `questions_for_departments` returns an empty tuple and `may_be_asked`
        # withholds every department block, which is the correct reading of "we do not
        # know yet" rather than a gap to fill.
        why=(
            "Each one you pick adds five questions only that department can answer, "
            "and unlocks its director. Each one you leave out stays absent rather "
            "than empty. You can pick them later, from the department itself."
        ),
        options=SCOREABLE_DEPARTMENTS,
    ),
    # Doc 04 §5 stage 4. **Answering this connects nothing**, and the wording says
    # so: no connector is built (M10 — and D3 and D10 are still open), so the only
    # honest thing to collect is which of these the customer actually has. It is
    # worth collecting anyway: it decides which Locked tiles are a real unlock for
    # this company and which are irrelevant to it.
    Question(
        key="tools_available",
        prompt="Which of these does your company use?",
        stage=Pass.CONNECT,
        answer_type=AnswerType.MULTI_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why=(
            "Nothing is connected by answering - no connector is built yet. It tells "
            "us which locked capabilities are worth unlocking for you first."
        ),
        options=CONNECTABLE_TOOLS,
    ),
    # ── After team invitation (doc 06 §4.10) ──────────────────
    Question(
        key="brief_recipients",
        prompt="Who should receive the daily brief?",
        stage=Pass.POST_INVITE,
        answer_type=AnswerType.USER_LIST,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="Recipients must be people in this workspace.",
    ),
    *DEPARTMENT_QUESTIONS,
)

BY_KEY: dict[str, Question] = {q.key: q for q in CATALOGUE}


def questions_for(stage: Pass) -> tuple[Question, ...]:
    return tuple(q for q in CATALOGUE if q.stage is stage)


def questions_for_departments(selected: frozenset[Department]) -> tuple[Question, ...]:
    """The department block, narrowed to the departments a company runs.

    An unselected department's questions are **absent**, not disabled: doc 08 §2.2's
    principle applied to the form itself — a channel the company does not run is
    reported as *not run* rather than as zero, and a department it does not have
    should not be a row of greyed-out inputs implying it forgot something.
    """
    return tuple(
        q for q in DEPARTMENT_QUESTIONS if q.asked_of is not None and q.asked_of in selected
    )


def scope_for_answer(key: str) -> tuple[Scope, Department | None]:
    """The classification to store with an answer.

    Raises on an unknown key rather than defaulting. An answer whose scope we
    cannot name must not be stored at a guessed one — that is I4's default-deny
    applied to capture rather than to classification.
    """
    question = BY_KEY.get(key)
    if question is None:
        raise KeyError(f"Unknown onboarding question: {key}")
    return question.scope, question.department
