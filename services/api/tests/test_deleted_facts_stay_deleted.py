"""Q62 — a deleted fact is not silently re-inferred.

`review_gate` has stated this rule in its module docstring since P13 was
designed and nothing has enforced it. A rule that lives only in prose is one the
next crawl breaks without failing anything, which is precisely the shape of
defect this codebase keeps finding.

Deleting is not "remove the row". It says *this is wrong about my business*, and
re-deriving it on the next run tells the founder their correction did not
matter. So the deletion is itself a fact about the company, and it has to
outrank the source that produced the original.
"""

from __future__ import annotations

import pytest

from app.domain.facts import SourceKind
from app.domain.review_gate import Deletion, may_infer


def _deleted(key: str = "headcount") -> Deletion:
    return Deletion(key=key, reason="We are eleven people, not four.")


def test_a_deletion_needs_a_reason() -> None:
    """Delete-with-a-reason, per P13. A reason is what makes the deletion a
    fact about the company rather than an absence somebody has to interpret —
    and it is the only thing that tells a later reader why the crawl was wrong."""
    with pytest.raises(ValueError):
        Deletion(key="headcount", reason="   ")


def test_a_crawl_may_not_reinfer_what_a_person_deleted() -> None:
    """The whole point of Q62."""
    assert not may_infer("headcount", SourceKind.CRAWL, deletions=[_deleted()])


def test_an_inference_may_not_reinfer_it_either() -> None:
    """Weaker than a crawl, so this must not be the one that gets through."""
    assert not may_infer("headcount", SourceKind.INFERENCE, deletions=[_deleted()])


def test_an_untouched_key_is_unaffected() -> None:
    """Deleting one fact must not quietly suppress the rest of the brain."""
    assert may_infer("revenue", SourceKind.CRAWL, deletions=[_deleted()])


def test_the_person_may_state_it_again_themselves() -> None:
    """A deletion binds *derivation*, not the founder.

    Refusing their own re-entry would make the delete button a trap: get it
    wrong once and the field is dead forever, with no way back that does not
    involve support.
    """
    assert may_infer("headcount", SourceKind.USER_CONFIRMED, deletions=[_deleted()])


def test_a_connected_system_may_state_it_again() -> None:
    """A payroll system saying the headcount is a measurement, not a guess.

    This is the line worth being deliberate about: the founder deleted what a
    *crawl* inferred, and a connected system is the thing that outranks a crawl
    everywhere else in `facts.py`. Suppressing it here would mean the delete
    button silently disconnects a tool the founder chose to plug in.
    """
    assert may_infer("headcount", SourceKind.CONNECTED_SYSTEM, deletions=[_deleted()])
