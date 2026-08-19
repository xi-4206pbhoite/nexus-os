"""Onboarding answers are scope-tagged at capture.

Doc 06 §2.5: *"Onboarding answers carry scope like anything else... They are not
'company facts' visible to everyone merely because they arrived through a
form."*

The whole point is that a form is not a laundering mechanism. Typing your
average deal size into onboarding does not make it public within the company,
and a catalogue that quietly omitted a scope would default it to whatever the
storage layer used.
"""

from __future__ import annotations

import pytest

from app.domain.onboarding import (
    BY_KEY,
    CATALOGUE,
    Pass,
    questions_for,
    scope_for_answer,
)
from app.domain.scopes import Department, Scope

# ── Every answer is classified ────────────────────────────────


def test_every_question_carries_a_scope() -> None:
    for question in CATALOGUE:
        assert isinstance(question.scope, Scope), f"{question.key} has no scope"


def test_every_l3_question_names_its_department() -> None:
    """An L3 fact with no department cannot be filtered by department."""
    for question in CATALOGUE:
        if question.scope is Scope.L3_DEPARTMENT:
            assert question.department is not None, f"{question.key} is L3 with no department"


def test_no_question_above_l3_is_collected_at_onboarding() -> None:
    """L4 and L5 are not things a signup form should be creating."""
    for question in CATALOGUE:
        assert question.scope <= Scope.L3_DEPARTMENT, f"{question.key} is {question.scope}"


def test_keys_are_unique() -> None:
    assert len(BY_KEY) == len(CATALOGUE)


def test_an_unknown_key_raises_rather_than_defaulting() -> None:
    """An answer whose scope we cannot name must not be stored at a guessed one."""
    with pytest.raises(KeyError):
        scope_for_answer("some_field_someone_added_in_a_hurry")


# ── The two doc 06 §2.5 names explicitly ──────────────────────


def test_average_deal_size_is_l3_sales_not_a_company_fact() -> None:
    scope, department = scope_for_answer("average_deal_size")
    assert scope is Scope.L3_DEPARTMENT
    assert department is Department.SALES


def test_marketing_budget_is_l3_finance_not_a_company_fact() -> None:
    scope, department = scope_for_answer("monthly_marketing_budget")
    assert scope is Scope.L3_DEPARTMENT
    assert department is Department.FINANCE


@pytest.mark.parametrize("key", ["average_deal_size", "monthly_marketing_budget"])
def test_the_sensitive_answers_are_not_company_public(key: str) -> None:
    """The failure this guards: a Viewer reading the company's deal size
    because it was typed into a form rather than imported from a CRM."""
    scope, _ = scope_for_answer(key)
    assert scope is not Scope.L1_COMPANY_PUBLIC
    assert scope is not Scope.L2_COMPANY_INTERNAL


# ── Only genuinely public things are L1 ───────────────────────


def test_l1_is_reserved_for_material_that_leaves_the_company() -> None:
    """Every member of this set has to be defensible as *published*.

    `company_name` and `what_we_sell` joined it on the same argument the brand-voice
    questions already carry: a company's own name and what it sells are outward-facing
    by nature, and both feed generated copy that leaves the building. `your_name` did
    **not** — a person's name is not published material merely because their
    employer's services are, so it sits at L2.
    """
    l1_keys = {q.key for q in CATALOGUE if q.scope is Scope.L1_COMPANY_PUBLIC}
    assert l1_keys == {
        "company_url",
        "company_name",
        "what_we_sell",
        "forbidden_terms",
        "preferred_terms",
    }, "L1 means published or outward-facing. Anything else belongs at L2 or above."


# ── Sequencing (doc 04 §5, doc 06 §4.10) ──────────────────────


AUDIT_NEEDS = {"company_url", "stated_purpose"}
"""What doc 04 §5 licenses asking before anything has been shown.

`role` and `department` were in this set and are not any more. They were never read
by the audit, so their membership here was never earned by this test's own rule —
what kept them was that they were *required*, which is the opposite of a
justification. They are Pass 2 questions now, and optional ones.

The person answering Pass 1 is always the Owner who just cleared the domain gate,
and their real role and department are already in `membership` — the only record
that decides anything. Two mandatory dropdowns whose help text has to explain that
the answer does not do what it looks like it does are two dropdowns worth deferring.
"""

IDENTITY = {"your_name", "company_name"}
"""The two exceptions, and they are exceptions rather than a widening.

Doc 04 §5's rule is that the audit earns the right to ask. Neither of these is
needed by the audit, so admitting them **is** a relaxation of it — recorded here
rather than absorbed by loosening the assertion.

What justifies them: registration names the workspace from the email domain
(ADR 0013), so without these the company is called `acmetrading.om` on every
screen and the assistant addresses the user by their email address. Both cost the
user no thought, which is the property that makes them harmless before the audit —
and is exactly what a third addition would have to argue for too.
"""


def test_pass_one_asks_only_the_audit_and_identity() -> None:
    """Doc 04 §5 — the audit comes before the questionnaire, because it is the
    only moment that earns the right to ask for the rest.

    Still an exact set: the point is that anything new has to justify itself in one
    of the two buckets above, not that Pass 1 is now open.
    """
    keys = {q.key for q in questions_for(Pass.ONE)}
    assert keys == AUDIT_NEEDS | IDENTITY


def test_pass_one_is_four_questions() -> None:
    """The number is the point, so it is asserted rather than left to the set above.

    Signup is the whole of Pass 1. Its length is what decides whether anyone reaches
    the product, so growing it should require deleting this line and arguing for the
    new number — not merely adding a `Question`.
    """
    assert len(questions_for(Pass.ONE)) == 4


def test_the_identity_questions_are_not_required() -> None:
    """They are conveniences, so they must not block a user from reaching the audit.

    `company_url` is the only Pass 1 answer the audit cannot run without.
    """
    by_key = {q.key: q for q in questions_for(Pass.ONE)}
    for key in IDENTITY:
        assert by_key[key].required is False


def test_company_url_is_the_only_required_answer_anywhere() -> None:
    """Nothing else may block a user out of their own workspace.

    Five questions were `required`: `company_url`, `role`, `department`, `currency`,
    `fiscal_year_start` and `departments_run`. Four of them gated completion on facts
    no built surface reads — a currency for figures that do not render yet, a fiscal
    year for period comparisons that do not exist, a department selection whose only
    effect is to *add* twenty-eight further questions.

    `company_url` stays, because the audit genuinely cannot run without a site to
    read, and `complete_setup` marking a workspace ready with nothing to crawl is the
    failure that made `required` server-enforced in the first place.
    """
    required = {q.key for q in CATALOGUE if q.required}
    assert required == {"company_url"}


def test_money_questions_are_never_in_pass_one() -> None:
    """Doc 04 §2e — asking for financial figures before showing anything is
    what makes people abandon a form."""
    for question in questions_for(Pass.ONE):
        assert question.scope is not Scope.L3_DEPARTMENT


def test_brief_recipients_comes_after_team_invitation() -> None:
    """Doc 06 §4.10 — recipients must be workspace users, so they cannot be
    chosen from a list that does not exist yet."""
    assert BY_KEY["brief_recipients"].stage is Pass.POST_INVITE


def test_every_stage_has_questions() -> None:
    for stage in Pass:
        assert questions_for(stage), f"{stage} has no questions"


# ── Explanations ──────────────────────────────────────────────


def test_required_questions_explain_themselves() -> None:
    """Doc 04 §5 — each request should be justified by something already seen."""
    for question in CATALOGUE:
        if question.required:
            assert question.why, f"{question.key} is required but unexplained"


def test_the_two_money_questions_explain_what_they_unlock() -> None:
    for key in ("average_deal_size", "monthly_marketing_budget"):
        assert BY_KEY[key].why, f"{key} asks for a financial figure without saying why"
