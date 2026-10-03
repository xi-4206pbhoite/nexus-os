"""One code path from sources to facts. **No module builds its own context.**

`doc/12` P13 states it as a rule, and the reason is I1. Every fact must be able
to name where it came from, and the moment two modules assemble facts their own
way, one of them forgets — not through carelessness but because `source_ref` is
the easiest field to leave for later. So there is one function, it takes a
source, and it cannot produce a fact without one.

**Assembly proposes; `decide` disposes.** This turns raw material into candidate
facts and hands each to `facts.decide`, which holds the precedence rule. Putting
precedence here as well would mean two places that must agree about which fact
wins — and they would, until they did not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.domain.facts import Incumbent, SourceKind, WriteOutcome, decide


@dataclass(frozen=True, slots=True)
class Candidate:
    """A fact we are proposing, with where it came from already attached.

    `source_ref` has no default and is not optional. A fact whose source cannot
    be opened is a fact nobody can check, and the product's entire claim is that
    every number can be.
    """

    key: str
    value: str
    source_kind: SourceKind
    source_ref: str
    confidence: float
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class Applied:
    """What happened to one candidate. Returned rather than logged, so a caller
    can show the founder which sources actually changed anything."""

    candidate: Candidate
    outcome: WriteOutcome


def from_onboarding_answer(*, question_key: str, value: str, is_assumption: bool) -> Candidate:
    """A founder's own answer.

    **An assumption is not `user_confirmed`.** They said "not sure" and we
    proceeded on a stated basis — recording that as confirmed would make the
    product's own guess indistinguishable from their testimony, and every later
    contradiction would then be treated as contradicting *them*.
    """
    return Candidate(
        key=question_key,
        value=value,
        source_kind=SourceKind.INFERENCE if is_assumption else SourceKind.USER_CONFIRMED,
        source_ref=f"onboarding:{question_key}",
        confidence=0.6 if is_assumption else 1.0,
    )


def from_crawled_page(*, key: str, value: str, url: str, confidence: float) -> Candidate:
    """Read from the company's own site. `source_ref` is the URL, so a founder
    can open the page the claim came from."""
    return Candidate(
        key=key,
        value=value,
        source_kind=SourceKind.CRAWL,
        source_ref=url,
        confidence=confidence,
    )


def from_document_chunk(*, key: str, value: str, chunk_id: str, confidence: float) -> Candidate:
    """Extracted from an upload. The ref is the **chunk**, not the document: a
    citation that opens a forty-page PDF and leaves somebody to find the
    sentence is a citation in name only."""
    return Candidate(
        key=key,
        value=value,
        source_kind=SourceKind.DOCUMENT,
        source_ref=f"chunk:{chunk_id}",
        confidence=confidence,
    )


MIN_CONFIDENCE: Final = 0.5
"""Below this a candidate is not proposed at all.

Not a second permission gate — the classifier's threshold governs *visibility*,
this governs whether something is worth asserting as a fact at all. A fact
nobody believes is noise in the review queue rather than a finding, and a review
queue full of noise is one people stop reading.
"""


def apply(candidates: list[Candidate], held: dict[str, Incumbent]) -> list[Applied]:
    """Run every candidate past the precedence rule, in one place.

    `held` is **not** mutated as candidates are applied. Resolving two
    candidates for the same key against each other is the review gate's job, not
    assembly's — silently letting the later one win would be exactly the recency
    rule `facts.wins` refuses.
    """
    return [
        Applied(
            candidate=candidate,
            outcome=(
                WriteOutcome.REJECTED
                if candidate.confidence < MIN_CONFIDENCE
                else decide(
                    candidate_value=candidate.value,
                    candidate_kind=candidate.source_kind,
                    incumbent=held.get(candidate.key),
                )
            ),
        )
        for candidate in candidates
    ]
