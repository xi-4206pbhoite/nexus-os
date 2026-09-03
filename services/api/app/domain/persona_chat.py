"""The persona interview — a chat that learns how to present, never what to show.

`doc/05` §2.6, already enforced as an invariant in
`tests/test_persona_and_invitations.py`:

> No persona field is ever an input to the retrieval predicate.

**This is the rule a personalisation feature quietly breaks.** A chat that
concludes "this person is a finance lead" must not widen what finance data they
can reach — that is `ScopedSession`'s job and its alone. The persona says *what
to lead with*; permission says *what may be led with*. `ScopedSession` carries
no persona field, so the mistake cannot compile, and this module returns a
`Persona` that has no way to reach a query.

**Scripted, and a model is optional (ADR 0011).** The interview is a fixed
sequence of questions with a next-question function, so the persona is built the
same way with or without an API key. A language model, when configured, makes
the wording conversational — it does not decide what is asked or what is
stored. A model that could invent `seniority` would be inventing an authority
claim in the one place the product cannot afford one.

The person's **role and departments come from their invitation**, never from
this conversation. Somebody typing "I'm the CFO" into a chat box is not a
promotion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    prompt: str
    why: str
    """What this changes for them. Every question says so, for the same reason
    the onboarding bank does: a question whose point you cannot see is one you
    resent answering."""
    choices: tuple[str, ...] = ()
    free_text: bool = True


INTERVIEW: Final[tuple[Question, ...]] = (
    Question(
        key="stated_purpose",
        prompt="In a sentence, what do you actually use this for day to day?",
        why="What your home screen opens on.",
    ),
    Question(
        key="priority_topics",
        prompt="Which two or three things do you want to hear about first?",
        why="What gets surfaced before everything else.",
    ),
    Question(
        key="communication_style",
        prompt="Would you rather have the short answer or the full working?",
        why="How much detail comes with every answer.",
        choices=("the short answer", "the full working", "short first, working on request"),
        free_text=False,
    ),
    Question(
        key="language",
        prompt="Which language should NEXUS reply in?",
        why="The language of every answer and summary.",
        choices=("English", "العربية", "both"),
        free_text=False,
    ),
)

ANSWERABLE: Final[frozenset[str]] = frozenset(q.key for q in INTERVIEW)

# Not asked, and deliberately absent rather than merely unused. `seniority`
# reads like a persona field and is an authority claim; it is set from the
# invitation's role, which somebody else chose. Q32's shape: a rule expressed as
# an absence, so nobody wires it up later without meeting this comment.
never_asked: Final[tuple[str, ...]] = ("seniority", "role", "departments")


@dataclass(slots=True)
class Persona:
    """What the interview produced. It has no route to a query, by construction."""

    stated_purpose: str | None = None
    priority_topics: list[str] = field(default_factory=list)
    communication_style: str | None = None
    language: str | None = None

    @property
    def complete(self) -> bool:
        return bool(self.stated_purpose and self.priority_topics)


def next_question(answered: dict[str, str]) -> Question | None:
    """The first unanswered question, or `None` when the interview is done.

    A function of what has been answered rather than a cursor the client keeps,
    so a person who closes the tab resumes where they left off — the same reason
    onboarding is resumable (Q28).
    """
    for question in INTERVIEW:
        # `.strip()`, because `"   "` is truthy and would advance the interview
        # on an empty box — building a persona out of nothing. The department
        # block had exactly this defect, and it marked questions answered that
        # held an empty string.
        if not answered.get(question.key, "").strip():
            return question
    return None


def apply(answered: dict[str, str]) -> Persona:
    """Turn the answers into a persona. Only known keys, only stated values."""
    topics = [t.strip() for t in answered.get("priority_topics", "").split(",") if t.strip()]
    return Persona(
        stated_purpose=answered.get("stated_purpose") or None,
        priority_topics=topics,
        communication_style=answered.get("communication_style") or None,
        language=answered.get("language") or None,
    )
