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


# ── The write path (P13) ──────────────────────────────────────


def test_a_lower_precedence_source_never_overwrites() -> None:
    """`doc/12` P13, and enforced **on write**.

    A read-time rule is one every future reader has to remember. A write-time
    rule is one the data cannot violate.
    """
    from app.domain.facts import Incumbent, WriteOutcome, decide

    confirmed = Incumbent(value="OMR 2.4m", source_kind=SourceKind.USER_CONFIRMED, confirmed=True)
    assert (
        decide(candidate_value="OMR 9m", candidate_kind=SourceKind.DOCUMENT, incumbent=confirmed)
        is not WriteOutcome.STORED
    )


def test_contradicting_a_person_asks_rather_than_rejects() -> None:
    """*Re-confirmation, not overwrite.*

    Deliberately not `rejected`. A crawl disagreeing with a confirmed figure is
    evidence the world may have moved, and silently discarding it means the
    founder is never told their confirmed number may be stale. The value does
    not change; somebody is asked to look again.
    """
    from app.domain.facts import Incumbent, WriteOutcome, decide

    confirmed = Incumbent(value="12 staff", source_kind=SourceKind.USER_CONFIRMED, confirmed=True)
    assert (
        decide(candidate_value="30 staff", candidate_kind=SourceKind.CRAWL, incumbent=confirmed)
        is WriteOutcome.NEEDS_RECONFIRMATION
    )


def test_agreement_is_settled_before_anything_else() -> None:
    """A crawl that confirms what a person typed is neither a conflict nor a
    change. Treating it as either fills the history with noise and — worse —
    asks the founder to re-confirm something nothing disputes."""
    from app.domain.facts import Incumbent, WriteOutcome, decide

    confirmed = Incumbent(value="12 staff", source_kind=SourceKind.USER_CONFIRMED, confirmed=True)
    assert (
        decide(candidate_value=" 12 staff ", candidate_kind=SourceKind.CRAWL, incumbent=confirmed)
        is WriteOutcome.UNCHANGED
    )


def test_a_higher_precedence_source_replaces_an_unconfirmed_fact() -> None:
    """The ordinary case: nobody has ruled on it, and something better arrived."""
    from app.domain.facts import Incumbent, WriteOutcome, decide

    inferred = Incumbent(value="guessed", source_kind=SourceKind.INFERENCE, confirmed=False)
    assert (
        decide(candidate_value="read it", candidate_kind=SourceKind.CRAWL, incumbent=inferred)
        is WriteOutcome.STORED
    )


def test_an_empty_key_is_simply_stored() -> None:
    from app.domain.facts import WriteOutcome, decide

    assert (
        decide(candidate_value="first", candidate_kind=SourceKind.DOCUMENT, incumbent=None)
        is WriteOutcome.STORED
    )


def test_no_source_can_silently_change_a_confirmed_value() -> None:
    """Exhaustive over every source kind. The guarantee is about *all* of them,
    and a confirmed fact is the strongest claim in the system — it is the one
    place a person has said "yes, this"."""
    from app.domain.facts import Incumbent, WriteOutcome, decide

    confirmed = Incumbent(value="held", source_kind=SourceKind.USER_CONFIRMED, confirmed=True)
    for kind in SourceKind:
        outcome = decide(candidate_value="different", candidate_kind=kind, incumbent=confirmed)
        if kind is SourceKind.USER_CONFIRMED:
            # Only a person overrides a person, and only by saying so again.
            continue
        assert outcome is WriteOutcome.NEEDS_RECONFIRMATION, kind
