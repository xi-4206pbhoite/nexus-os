"""The persona interview learns how to present, never what to show.

`doc/05` §2.6 is already an invariant in `test_persona_and_invitations.py`:
no persona field is ever an input to the retrieval predicate. These tests guard
the *chat* that fills the persona, which is where that rule is easiest to break
— a conversation is exactly the place someone would let a person describe
themselves into more access.
"""

from __future__ import annotations

import dataclasses

from app.domain.persona_chat import (
    ANSWERABLE,
    INTERVIEW,
    Persona,
    apply,
    never_asked,
    next_question,
)


def test_the_interview_never_asks_for_authority() -> None:
    """The one that matters.

    Role and departments come from the invitation, which somebody else issued.
    Somebody typing "I'm the CFO" into a chat box is not a promotion, and a
    persona interview is precisely where that would feel natural to allow.
    """
    for forbidden in never_asked:
        assert forbidden not in ANSWERABLE, forbidden
        assert not any(forbidden in q.prompt.lower() for q in INTERVIEW), forbidden


def test_a_persona_carries_no_field_that_could_widen_access() -> None:
    """`Persona` is presentation only, by construction.

    If a future field like `seniority` or `departments` appears here, it can be
    read by whatever renders the dashboard — and the next step, always, is
    somebody using it to decide what to fetch.
    """
    fields = {f.name for f in dataclasses.fields(Persona)}
    assert fields == {"stated_purpose", "priority_topics", "communication_style", "language"}
    for forbidden in never_asked:
        assert forbidden not in fields


def test_every_question_says_what_it_changes() -> None:
    """A question whose point you cannot see is one you resent answering — the
    same rule the onboarding bank follows."""
    for question in INTERVIEW:
        assert question.why.strip(), question.key
        assert question.why.endswith("."), question.key


def test_the_interview_resumes_where_it_was_left() -> None:
    """A function of what has been answered, not a cursor the client keeps, so
    closing the tab loses nothing (Q28)."""
    assert next_question({}) is INTERVIEW[0]

    answered = {"stated_purpose": "Watching cash"}
    assert next_question(answered) is INTERVIEW[1]

    everything = {q.key: "something" for q in INTERVIEW}
    assert next_question(everything) is None


def test_a_blank_answer_does_not_count_as_answered() -> None:
    """Otherwise an empty box advances the interview and the persona is built
    from nothing — the same defect the department block had."""
    assert next_question({"stated_purpose": "   "}) is INTERVIEW[0]


def test_only_stated_values_reach_the_persona() -> None:
    persona = apply(
        {
            "stated_purpose": "Watching cash",
            "priority_topics": "receivables, runway",
            "communication_style": "the short answer",
            "language": "English",
            # An unknown key, as a client could send. It must not appear.
            "seniority": "CFO",
        }
    )
    assert persona.stated_purpose == "Watching cash"
    assert persona.priority_topics == ["receivables", "runway"]
    assert not hasattr(persona, "seniority")
    assert persona.complete


def test_an_unfinished_interview_is_not_complete() -> None:
    assert not apply({"stated_purpose": "Watching cash"}).complete
