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

from app.domain.scopes import Department, Role, Scope


class Pass(StrEnum):
    """Doc 06 §2.5 — two passes, separated by the audit.

    Pass 1 is what is needed to run the audit. Pass 2 is asked *after* the user
    has seen something real about their own business, which is the only moment
    that earns the right to ask for the rest (doc 04 §5).
    """

    ONE = "pass_1"
    TWO = "pass_2"
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


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    prompt: str
    stage: Pass
    answer_type: AnswerType
    scope: Scope
    department: Department | None
    """The department that owns this fact at L3. `None` for L1/L2 facts."""
    required: bool = False
    why: str = ""
    """Shown to the user. Doc 04 §5 — every question should be justified by
    something they have already seen."""
    options: tuple[Choice, ...] = ()
    """The permitted answers, when the set is genuinely closed.

    Empty means free entry, and `USER_LIST` is a third case: its options are the
    workspace's current members, which are not knowable here — doc 06 §4.10 is
    the reason, and resolving them per workspace is the route's job.
    """

    assumption_when_unsure: str | None = None
    """What is recorded when a founder answers "not sure yet".

    **Not a default and not a null.** A null says nobody was asked; this says
    somebody was asked, did not know, and the product proceeded on a stated
    basis — which the Brain can later contradict with evidence, and a null
    cannot. It is also the difference between a blank dashboard tile and one
    that says what it is assuming.
    """

    consumed_by: str = ""
    """The capability that reads this answer. **Q33's whole rule.**

    A question with no consumer is not a question, it is a form field — and a
    form field costs a founder the same attention as a real question while
    changing nothing they will ever see. `tests/test_question_bank.py` fails on
    an unconsumed question, which is the guard against this drifting back
    towards the thirty-nine an earlier draft carried.

    A capability name, not a table or a function: what matters is that a person
    can trace a question to the thing that stops working without it, and argue
    about whether that thing earns the question.

    Empty on the company-stage questions — they are consumed by everything, and
    naming one consumer would be arbitrary. The test scopes its rule to the
    department bank for that reason.
    """

    confirmable_from_crawl: bool = False
    """Q20's crawl-then-confirm posture.

    A flagged question is **not asked during onboarding**. The research run
    proposes it and the founder confirms it at the review gate, because asking
    somebody for what we are about to find out ourselves spends the scarcest
    thing onboarding has — their patience — on a question we can answer.
    Industry is the first such field.
    """

    @property
    def free_entry(self) -> bool:
        return not self.options and self.answer_type is not AnswerType.USER_LIST


CATALOGUE: tuple[Question, ...] = (
    # ── Pass 1: enough to run the audit ───────────────────────
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
    # These two are **stated facts, not grants**. Answering them writes a row in
    # `onboarding_answer`; it never touches `membership`, which is the only thing
    # `build_scope` reads and therefore the only thing that authorises anything.
    # Doc 06 §2.2 — a self-declared role is privilege escalation via dropdown, so
    # the escalation has to be impossible rather than merely unimplemented.
    Question(
        key="role",
        prompt="What is your role?",
        stage=Pass.ONE,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        required=True,
        why=(
            "It shapes what your assistant leads with. It does not change what you "
            "can see — that comes from your membership, not from this answer."
        ),
        options=_choices(Role, {"external": "External / Client"}),
    ),
    Question(
        key="department",
        prompt="Which department is that in?",
        stage=Pass.ONE,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        required=True,
        # Doc 06 §2.3 — derived from role, confirmable, Owner-overridable.
        why="Derived from your role. Correct it if it is wrong.",
        options=_choices(Department, {"hr": "HR / People"}),
    ),
    Question(
        key="stated_purpose",
        prompt="What do you want help with most?",
        stage=Pass.ONE,
        answer_type=AnswerType.LONG_TEXT,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="It shapes what your assistant leads with.",
    ),
    # ── Pass 2: after the audit ───────────────────────────────
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
    ),
    Question(
        key="currency",
        prompt="Which currency do you report in?",
        stage=Pass.TWO,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        required=True,
        why="Every figure in the product is shown in it.",
        options=CURRENCIES,
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
)

BY_KEY: dict[str, Question] = {q.key: q for q in CATALOGUE}
"""Rebuilt below to include Phase 6's company stage — see `_register_p6`.

Three keys used to live in `CATALOGUE` and now live in `COMPANY_QUESTIONS`:
`ideal_customer`, `biggest_challenges` and `fiscal_year_start`. They were
removed above rather than left in place, because two `Question`s with one key is
a lookup that silently returns whichever was defined first — which is exactly
what happened: the P6 versions carried an assumption, and `BY_KEY` kept handing
out the old ones that did not.
"""


def questions_for(stage: Pass) -> tuple[Question, ...]:
    return tuple(q for q in CATALOGUE if q.stage is stage)


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


# ── Phase 6: the company stage (Q19) ──────────────────────────
#
# Five questions, and the count is the design. Doc 04 §5 wants every question
# justified by something the founder has already seen; five is what fits before
# the justification runs out and it starts feeling like a form.
#
# They are also the five a founder can answer **without going to look anything
# up**, except the fiscal year — which is why that one carries the assumption
# most likely to be used.
#
# `CATALOGUE` above is not deleted. It holds the department and persona
# questions P7 rebuilds into blocks, and deleting it here would take working,
# tested scope-tagging with it for the sake of tidiness.

COMPANY_QUESTIONS: tuple[Question, ...] = (
    Question(
        key="what_you_sell",
        prompt="What does your company sell?",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        scope=Scope.L1_COMPANY_PUBLIC,
        department=None,
        required=True,
        why="Everything NEXUS says about your market starts here.",
        assumption_when_unsure=(
            "Assumed from the website until confirmed — the research run will "
            "propose a description and you can correct it."
        ),
    ),
    Question(
        key="ideal_customer",
        prompt="Who is your ideal customer?",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="Lead scoring, outreach and content all judge against this.",
        assumption_when_unsure=(
            "Assumed to be whoever your current customers resemble, until you say otherwise."
        ),
    ),
    Question(
        key="top_goals",
        prompt="Your top three goals for the next year",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="What NEXUS measures progress against, and what it recommends towards.",
        assumption_when_unsure=(
            "Assumed to be growth in revenue, until you name something else. "
            "Stated plainly because a wrong goal quietly bends every "
            "recommendation towards it."
        ),
    ),
    Question(
        key="biggest_challenges",
        prompt="Your biggest challenges right now",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="What the morning brief looks for first.",
        assumption_when_unsure="None stated — the brief will surface what it finds instead.",
    ),
    Question(
        key="fiscal_year_start",
        prompt="When does your financial year start?",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="Every quarter, every year-to-date figure and every comparison depends on it.",
        assumption_when_unsure=(
            "Assumed to be January. Wrong for most of the GCC, which is exactly "
            "why it is stated rather than silently defaulted — a misaligned "
            "fiscal year makes every year-to-date number wrong without making "
            "any of them look wrong."
        ),
    ),
)


# Q20. Asked by the crawl, confirmed at the review gate, never asked here.
CONFIRMABLE_FROM_CRAWL: tuple[Question, ...] = (
    Question(
        key="industry",
        prompt="What industry are you in?",
        stage=Pass.ONE,
        answer_type=AnswerType.TEXT,
        scope=Scope.L1_COMPANY_PUBLIC,
        department=None,
        why="Benchmarks and competitor discovery both key off it.",
        confirmable_from_crawl=True,
        assumption_when_unsure="Taken from your website, for you to confirm.",
    ),
)


@dataclass(frozen=True, slots=True)
class ResolvedAnswer:
    """What actually gets stored for one question."""

    value: str
    is_assumption: bool


def resolve_answer(question: Question, *, value: str | None, unsure: bool) -> ResolvedAnswer:
    """Turn what the founder did into what is stored.

    The whole point of Phase 6's "not sure yet": it must **never** produce a
    null. A null is indistinguishable from a question nobody reached, so the
    product cannot tell "we asked and they did not know" from "we never asked" —
    and those want different behaviour everywhere downstream, from the dashboard
    tile to the review gate to what the Brain is willing to assert.

    `is_assumption` travels with the value so a caller cannot store one and
    forget the other.
    """
    if unsure or value is None or not value.strip():
        assumption = question.assumption_when_unsure
        if assumption is None:
            raise ValueError(
                f"{question.key} has no assumption to fall back on, so "
                '"not sure yet" would store a null. Give it one, or make the '
                "question required."
            )
        return ResolvedAnswer(value=assumption, is_assumption=True)

    return ResolvedAnswer(value=value.strip(), is_assumption=False)


# Phase 6's questions join the lookup. Appended rather than merged into the
# literal above because `COMPANY_QUESTIONS` is defined after it, and a lookup
# that silently disagrees with the catalogue it indexes is worse than one built
# in two steps with a comment saying so.
BY_KEY.update({q.key: q for q in COMPANY_QUESTIONS})
BY_KEY.update({q.key: q for q in CONFIRMABLE_FROM_CRAWL})
