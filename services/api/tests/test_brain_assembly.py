"""One code path from sources to facts, and every fact names its source.

`doc/12` P13: *no module builds its own context.* The reason is I1 — the moment
two modules assemble facts their own way, one forgets the `source_ref`, not
through carelessness but because it is the easiest field to leave for later.
"""

from __future__ import annotations

import dataclasses

from app.domain.assembly import (
    MIN_CONFIDENCE,
    Candidate,
    apply,
    from_crawled_page,
    from_document_chunk,
    from_onboarding_answer,
)
from app.domain.facts import Incumbent, SourceKind, WriteOutcome


def test_a_candidate_cannot_exist_without_a_source() -> None:
    """`source_ref` has no default, so a fact with no traceable origin is a
    `TypeError` rather than a row somebody discovers later."""
    required = {f.name for f in dataclasses.fields(Candidate) if f.default is dataclasses.MISSING}
    assert "source_ref" in required
    assert "source_kind" in required


def test_an_assumption_is_never_recorded_as_the_founder_confirming_it() -> None:
    """The one that would quietly corrupt the trust model.

    They said "not sure" and we proceeded on a stated basis. Recording that as
    `user_confirmed` makes our own guess indistinguishable from their
    testimony — and every later contradiction would then be treated as
    contradicting *them*, which is both wrong and rude.
    """
    assumed = from_onboarding_answer(
        question_key="fiscal_year_start", value="January", is_assumption=True
    )
    assert assumed.source_kind is SourceKind.INFERENCE
    assert assumed.confidence < 1.0

    stated = from_onboarding_answer(
        question_key="what_you_sell", value="Dates", is_assumption=False
    )
    assert stated.source_kind is SourceKind.USER_CONFIRMED


def test_a_document_citation_points_at_the_chunk_not_the_file() -> None:
    """A citation that opens a forty-page PDF and leaves somebody to find the
    sentence is a citation in name only."""
    candidate = from_document_chunk(key="terms", value="Net 30", chunk_id="abc", confidence=0.9)
    assert candidate.source_ref == "chunk:abc"


def test_a_crawled_fact_carries_the_url_it_came_from() -> None:
    candidate = from_crawled_page(
        key="what_you_sell", value="Dates", url="https://example.om/about", confidence=0.8
    )
    assert candidate.source_ref.startswith("https://")


def test_a_fact_nobody_believes_is_not_proposed() -> None:
    """Not a second permission gate — the classifier's threshold governs
    visibility. This governs whether something is worth asserting at all, and a
    review queue full of noise is one people stop reading."""
    weak = from_crawled_page(
        key="revenue", value="OMR 9m", url="https://example.om", confidence=MIN_CONFIDENCE - 0.1
    )
    assert apply([weak], {})[0].outcome is WriteOutcome.REJECTED


def test_precedence_lives_in_one_place() -> None:
    """Assembly proposes; `decide` disposes. Two places holding the precedence
    rule would agree, until they did not."""
    confirmed = Incumbent(value="12", source_kind=SourceKind.USER_CONFIRMED, confirmed=True)
    crawled = from_crawled_page(
        key="headcount", value="30", url="https://example.om", confidence=0.9
    )

    applied = apply([crawled], {"headcount": confirmed})
    assert applied[0].outcome is WriteOutcome.NEEDS_RECONFIRMATION


def test_two_candidates_for_one_key_do_not_resolve_each_other() -> None:
    """`held` is not mutated as candidates are applied.

    Letting the later one win silently would be exactly the recency rule
    `facts.wins` refuses — resolving a disagreement between two sources is the
    review gate's job, not assembly's.
    """
    first = from_crawled_page(key="k", value="a", url="https://x.om", confidence=0.9)
    second = from_crawled_page(key="k", value="b", url="https://y.om", confidence=0.9)

    outcomes = [a.outcome for a in apply([first, second], {})]
    assert outcomes == [WriteOutcome.STORED, WriteOutcome.STORED], (
        "assembly must not decide between two candidates for the same key"
    )
