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

from app.domain.scopes import Department, Scope


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
    Question(
        key="role",
        prompt="What is your role?",
        stage=Pass.ONE,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        required=True,
        why="Your role decides which departments you can see.",
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
        key="biggest_challenges",
        prompt="What is getting in the way?",
        stage=Pass.TWO,
        answer_type=AnswerType.MULTI_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        why="It orders the improvement roadmap.",
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
    ),
    Question(
        key="fiscal_year_start",
        prompt="When does your financial year start?",
        stage=Pass.TWO,
        answer_type=AnswerType.SINGLE_CHOICE,
        scope=Scope.L2_COMPANY_INTERNAL,
        department=None,
        required=True,
        why="Period comparisons depend on it.",
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
