"""Which twenty pages, in what order, and when to stop.

`fetch_page` already solves the dangerous part — one page, SSRF-guarded, with
the guard re-applied at every redirect hop. These cover the layer above it,
where the decisions are, and they are pure: no network, no clock.
"""

from __future__ import annotations

from app.research.site import (
    HARD_CAP_SECONDS,
    JS_RENDERED_MESSAGE,
    MAX_PAGES,
    SOFT_CAP_SECONDS,
    Budget,
    links_in,
    looks_javascript_rendered,
    plan,
    priority_of,
    same_site,
    urls_in_sitemap,
)

SITE = "https://example.om"


def test_a_lookalike_host_is_not_the_same_site() -> None:
    """The one that would matter.

    `evil-example.om.attacker.net` contains `example.om`, and a crawler using a
    substring test would follow it — leaving the site it was asked about, and
    handing the SSRF guard a target nobody chose.
    """
    assert same_site("https://example.om/about", SITE)
    assert same_site("https://www.example.om/about", SITE)
    assert not same_site("https://example.om.attacker.net/", SITE)
    assert not same_site("https://notexample.om/", SITE)


def test_javascript_urls_are_not_pages() -> None:
    assert not same_site("javascript:alert(1)", SITE)
    assert not same_site("mailto:hi@example.om", SITE)


def test_the_pages_that_answer_onboarding_come_first() -> None:
    """A twenty-page budget spent on a blog archive tells us nothing about what
    a company sells."""
    ordered = plan(
        [
            f"{SITE}/blog/post-1",
            f"{SITE}/contact",
            f"{SITE}/",
            f"{SITE}/about-us",
            f"{SITE}/pricing",
        ],
        origin=SITE,
    )
    assert ordered[0] == f"{SITE}"
    assert ordered.index(f"{SITE}/about-us") < ordered.index(f"{SITE}/contact")
    assert ordered[-1] == f"{SITE}/blog/post-1"


def test_priority_matches_a_path_prefix_not_a_substring() -> None:
    """`/about-us` and `/about/team` are the about page; `/whereabouts` is not."""
    assert priority_of(f"{SITE}/about-us") == priority_of(f"{SITE}/about")
    assert priority_of(f"{SITE}/whereabouts") > priority_of(f"{SITE}/about")


def test_the_plan_is_stable_across_runs() -> None:
    """A crawl that varies run to run makes every difference in the Brain look
    like a change in the business."""
    candidates = [f"{SITE}/blog/{i}" for i in range(5)] + [f"{SITE}/pricing"]
    assert plan(candidates, origin=SITE) == plan(candidates, origin=SITE)


def test_duplicates_and_fragments_are_one_page() -> None:
    ordered = plan([f"{SITE}/about", f"{SITE}/about/", f"{SITE}/about#team"], origin=SITE)
    assert len(ordered) == 1


def test_the_budget_is_twenty_pages() -> None:
    ordered = plan([f"{SITE}/p{i}" for i in range(50)], origin=SITE)
    assert len(ordered) == MAX_PAGES


def test_the_soft_cap_stops_starting_and_the_hard_cap_abandons() -> None:
    """Two caps, because a crawl that is nearly done should be allowed to finish
    and one that has hung must not hold the run forever (D20)."""
    assert SOFT_CAP_SECONDS == 5 * 60
    assert HARD_CAP_SECONDS == 10 * 60

    nearly = Budget(pages_fetched=3, elapsed_seconds=SOFT_CAP_SECONDS + 1)
    assert nearly.exhausted, "past the soft cap, start nothing new"
    assert not nearly.must_abandon, "but let what is running finish"

    hung = Budget(pages_fetched=3, elapsed_seconds=HARD_CAP_SECONDS + 1)
    assert hung.must_abandon


def test_the_page_budget_alone_exhausts_it() -> None:
    assert Budget(pages_fetched=MAX_PAGES, elapsed_seconds=1).exhausted


def test_a_sitemap_is_read_before_guessing_from_links() -> None:
    """A sitemap is the site telling us what it considers a page, rather than us
    inferring it from navigation."""
    xml = "<urlset><url><loc>https://example.om/pricing</loc></url></urlset>"
    assert urls_in_sitemap(xml) == ["https://example.om/pricing"]

    html = '<a href="/about">About</a><a href="https://example.om/contact">Contact</a>'
    assert links_in(html, base_url=SITE) == [f"{SITE}/about", f"{SITE}/contact"]


def test_a_thin_page_full_of_script_is_a_shell_not_a_failure() -> None:
    """Q51. Both halves matter: text alone would flag a genuinely short page,
    and script volume alone would flag a content-rich page that also ships
    analytics. The combination means the words are assembled in a browser."""
    shell = "<html><body><div id='root'></div><script>" + ("x" * 5000) + "</script></body></html>"
    assert looks_javascript_rendered(shell, "")

    short_but_real = "<html><body><p>Call us on 1234.</p></body></html>"
    assert not looks_javascript_rendered(short_but_real, "Call us on 1234.")

    rich_with_analytics = (
        "<html><body>" + ("word " * 100) + "<script>" + ("y" * 5000) + "</script></body></html>"
    )
    assert not looks_javascript_rendered(rich_with_analytics, "word " * 100)


def test_the_shell_message_says_the_site_is_fine_and_what_happens_next() -> None:
    """ "We could not read your website" without those two reads as an accusation
    and offers no next step."""
    assert "Nothing is wrong" in JS_RENDERED_MESSAGE
    assert "instead" in JS_RENDERED_MESSAGE
