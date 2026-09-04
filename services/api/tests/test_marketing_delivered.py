"""Marketing's first real numbers, and the four ways they could lie.

`doc/12` P16. These are the first capabilities in the product to claim `live`,
so they are the first place the honesty rules stop being theoretical.
"""

from __future__ import annotations

from app.domain.dashboards import Source, WidgetState
from app.domain.marketing import (
    DELIVERED_MARKETING,
    KEYWORDS_LOCKED_REASON,
    marketing_state,
)

CRAWLED = True
NOTHING = frozenset[Source]()


def test_traffic_tiles_stay_planned_without_ga4() -> None:
    """3.1-3.3 are traffic, conversion and channel performance. None can be
    approximated from a crawl, so none of them pretends to be."""
    for offering in ("3.1", "3.2", "3.3"):
        assert marketing_state(offering, crawled=CRAWLED, connected=NOTHING) is (
            WidgetState.PLANNED
        )


def test_the_audits_are_live_on_a_crawl_alone() -> None:
    """They read crawl signals and nothing else, which is why they are the first
    two capabilities that can honestly say `live`."""
    for offering in DELIVERED_MARKETING:
        assert marketing_state(offering, crawled=CRAWLED, connected=NOTHING) is (WidgetState.LIVE)


def test_the_audits_are_not_partial_versions_of_a_ga4_number() -> None:
    """`PARTIAL` would imply connecting GA4 improves them. It does not — they
    measure the website and GA4 measures the visitors, and they are different
    numbers rather than two halves of one."""
    without = marketing_state("3.8", crawled=CRAWLED, connected=NOTHING)
    with_ga4 = marketing_state("3.8", crawled=CRAWLED, connected=frozenset({Source.GA4}))

    assert without is with_ga4 is WidgetState.LIVE


def test_no_crawl_locks_rather_than_showing_an_empty_score() -> None:
    """A built tile with nothing read yet has a missing *input*, not a missing
    implementation — and an audit score of zero would say the website failed
    every check rather than that we have not looked."""
    assert marketing_state("3.8", crawled=False, connected=NOTHING) is WidgetState.LOCKED


def test_the_keyword_half_says_it_is_absent_rather_than_estimating() -> None:
    """Q53/D2. A founder who expects keyword data should see that we know it is
    missing and why — not a page that never mentions it, and never a plausible
    estimate standing in for a measurement."""
    assert "not built" in KEYWORDS_LOCKED_REASON or "have not built" in KEYWORDS_LOCKED_REASON
    assert "estimated" in KEYWORDS_LOCKED_REASON
