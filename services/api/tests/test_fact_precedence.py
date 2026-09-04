"""`source_kind` **is** the precedence order (doc 06 §7.4).

Not a convention layered on the enum — it is why the enum is ordered, and the
whole reason a fact carries where it came from. These tests exist because
declaration order is load-bearing: a member added in the wrong place silently
changes which fact wins, and nothing else would notice.
"""

from __future__ import annotations

from app.domain.facts import PRECEDENCE, SourceKind, rank, wins


def test_the_order_is_what_doc_06_says() -> None:
    """Asserted literally, because the failure mode is somebody adding a member
    in the middle and every precedence decision changing under them."""
    assert [k.value for k in PRECEDENCE] == [
        "user_confirmed",
        "connected_system",
        "crawl",
        "inference",
        "document",
    ]


def test_a_person_beats_a_system() -> None:
    """They are the authority on their own business, and a system that disagrees
    is more likely misconfigured than right."""
    assert wins(SourceKind.USER_CONFIRMED, SourceKind.CONNECTED_SYSTEM)
    assert not wins(SourceKind.CONNECTED_SYSTEM, SourceKind.USER_CONFIRMED)


def test_a_live_system_beats_a_crawl_which_beats_a_guess() -> None:
    assert wins(SourceKind.CONNECTED_SYSTEM, SourceKind.CRAWL)
    assert wins(SourceKind.CRAWL, SourceKind.INFERENCE)
    assert wins(SourceKind.INFERENCE, SourceKind.DOCUMENT)


def test_a_tie_does_not_win() -> None:
    """The one that matters most.

    A second document disagreeing with the first does not replace it — that is a
    disagreement, and resolving it by recency would mean the last file uploaded
    quietly rewrites the company's facts. Equal precedence goes to the review
    gate, not to whoever arrived last.
    """
    for kind in SourceKind:
        assert not wins(kind, kind), kind


def test_precedence_is_transitive_across_every_pair() -> None:
    """Exhaustive rather than sampled: a precedence order with one inconsistent
    pair produces a fact that wins and loses against the same rival depending on
    which arrived first."""
    for a in SourceKind:
        for b in SourceKind:
            if a is b:
                continue
            assert wins(a, b) != wins(b, a), (a, b)
            if wins(a, b):
                assert rank(a) < rank(b)
