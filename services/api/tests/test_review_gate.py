"""What the review gate shows first, and what may be accepted without looking.

Three rules that look like presentation and are not: they decide which facts a
founder with finite attention actually checks, and whether "reviewed" means
anybody looked.
"""

from __future__ import annotations

from app.domain.review_gate import (
    MAX_THEMES,
    MIN_THEMES,
    TOP_FACTS,
    ReviewFact,
    Theme,
    assumptions,
    into_themes,
    rank,
    top,
)


def _fact(key: str, *, impact: int = 0, assumption: bool = False, theme: str = "t") -> ReviewFact:
    return ReviewFact(
        key=key,
        value="v",
        source_kind="crawl",
        source_ref="https://example.om",
        theme=theme,
        is_assumption=assumption,
        consumed_by=tuple(f"cap{i}" for i in range(impact)),
    )


def test_impact_is_dependency_count_not_confidence() -> None:
    """Q59. Ranking by confidence shows a founder what we are *least* sure of,
    which is the opposite of what matters — a low-confidence fact nothing uses
    is noise, and a high-confidence fact six dashboards read is worth their
    time."""
    ranked = rank([_fact("quiet", impact=0), _fact("busy", impact=6)])
    assert [f.key for f in ranked] == ["busy", "quiet"]


def test_an_assumption_outranks_a_stated_fact_of_equal_impact() -> None:
    """Of two facts nothing else distinguishes, the one the *product* invented
    deserves attention more than the one the founder told us."""
    ranked = rank([_fact("stated", impact=3), _fact("guessed", impact=3, assumption=True)])
    assert [f.key for f in ranked] == ["guessed", "stated"]


def test_the_order_is_stable_between_visits() -> None:
    """A screen that reshuffles makes a founder re-read what they already
    checked, which is how a review becomes a chore and then a rubber stamp."""
    facts = [_fact("b", impact=2), _fact("a", impact=2), _fact("c", impact=2)]
    assert [f.key for f in rank(facts)] == [f.key for f in rank(list(reversed(facts)))]


def test_bulk_accept_requires_the_theme_to_have_been_opened() -> None:
    """Q60. An "accept all" on a collapsed theme accepts things nobody has seen,
    and the entire purpose of this screen is that a person looked."""
    collapsed = Theme(name="Finance", facts=[_fact("k")], expanded=False)
    assert not collapsed.may_bulk_accept

    opened = Theme(name="Finance", facts=[_fact("k")], expanded=True)
    assert opened.may_bulk_accept


def test_an_empty_theme_cannot_be_bulk_accepted() -> None:
    """Accepting nothing should not be recordable as a review decision — it
    would put a confirmation in the audit trail that nobody made."""
    assert not Theme(name="Empty", facts=[], expanded=True).may_bulk_accept


def test_assumptions_are_a_separate_block() -> None:
    """ "We guessed this" is a different question from "is this right": the first
    asks the founder to supply something, the second to check it."""
    facts = [_fact("guessed", assumption=True), _fact("known")]
    assert [f.key for f in assumptions(facts)] == ["guessed"]


def test_themes_are_ordered_by_the_impact_they_contain() -> None:
    """A theme holding the single most-depended-upon fact belongs at the top
    even if it holds only that one."""
    themes = into_themes(
        [
            _fact("small", impact=1, theme="Marketing"),
            _fact("huge", impact=9, theme="Finance"),
            _fact("also-small", impact=1, theme="Marketing"),
        ]
    )
    assert [t.name for t in themes] == ["Finance", "Marketing"]


def test_the_screen_is_bounded() -> None:
    """A review that shows everything is one nobody finishes — and an unfinished
    review leaves facts unconfirmed while looking complete."""
    assert MIN_THEMES <= MAX_THEMES
    assert len(top([_fact(str(i), impact=i) for i in range(100)])) == TOP_FACTS
