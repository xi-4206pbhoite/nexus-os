"""Crawling a company's site: which pages, in what order, and when to stop.

`fetch_page` already solves the dangerous part — one page, SSRF-guarded, with
the guard re-applied at every redirect hop. This is the layer above it: **which
twenty pages are worth the budget**, and how to stop without lying about why.

Three decisions live here, all pure so they can be argued about without a
network.

**Priority is not crawl order for its own sake.** A twenty-page budget spent on
a blog archive tells us nothing about what a company sells. Home, about,
services, pricing and contact answer the questions onboarding is about to ask;
everything else is what is left over.

**The caps are a soft five minutes and a hard ten** (D20). The soft cap stops
starting new work; the hard cap abandons what is running. Two caps because a
crawl that is nearly done should be allowed to finish, and one that has hung
should not hold the run forever.

**A JavaScript shell is not a failure** (Q51). If the text is thin while the
script content dominates, the site rendered client-side — it is not broken, and
saying so would be wrong twice. The crawl records `js_rendered` and the run
continues with questions and documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import urljoin, urlparse

MAX_PAGES: Final = 20
SOFT_CAP_SECONDS: Final = 5 * 60
HARD_CAP_SECONDS: Final = 10 * 60

# In the order they answer onboarding's questions. Matched against the path, so
# `/about-us` and `/about` both count.
PRIORITY_PATHS: Final[tuple[str, ...]] = (
    "",  # the home page, always first
    "about",
    "services",
    "products",
    "pricing",
    "solutions",
    "contact",
    "blog",
)

# Below this, a "successful" fetch is almost certainly a shell.
MIN_TEXT_CHARS: Final = 200
# And above this ratio of script to text, it is certainly one.
SCRIPT_DOMINANCE: Final = 3.0

_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class Budget:
    """What is left. Pure, so the stop decision is testable without a clock."""

    pages_fetched: int
    elapsed_seconds: float

    @property
    def exhausted(self) -> bool:
        """Stop starting new work: the page budget or the soft cap is spent."""
        return self.pages_fetched >= MAX_PAGES or self.elapsed_seconds >= SOFT_CAP_SECONDS

    @property
    def must_abandon(self) -> bool:
        """Stop waiting for work already started. The hard cap.

        Separate from `exhausted` because a crawl that is nearly done should be
        allowed to finish, and one that has hung must not hold the run forever —
        the founder is watching a progress screen either way.
        """
        return self.elapsed_seconds >= HARD_CAP_SECONDS


def same_site(candidate: str, origin: str) -> bool:
    """Whether a discovered link belongs to the site being crawled.

    Host equality, not a substring test: `evil-example.com.attacker.net`
    contains `example.com`, and a crawler that followed it would leave the
    site it was asked about — and the SSRF guard would then be validating a
    target nobody chose.

    `www.` is ignored on both sides because it is the same site to everyone
    except a string comparison.
    """
    try:
        here, there = urlparse(candidate), urlparse(origin)
    except ValueError:
        return False
    if here.scheme not in ("http", "https"):
        return False
    return (
        here.hostname is not None
        and there.hostname is not None
        and (here.hostname.removeprefix("www.") == there.hostname.removeprefix("www."))
    )


def priority_of(url: str) -> int:
    """Lower sorts first. Unknown paths go last, in discovery order."""
    path = urlparse(url).path.strip("/").lower()
    if not path:
        return 0
    for rank, prefix in enumerate(PRIORITY_PATHS):
        if prefix and (
            path == prefix or path.startswith(f"{prefix}-") or path.startswith(f"{prefix}/")
        ):
            return rank
    return len(PRIORITY_PATHS)


def plan(candidates: list[str], *, origin: str, limit: int = MAX_PAGES) -> list[str]:
    """The pages to fetch, best first, de-duplicated and kept on-site.

    Stable within a priority band, so two runs over the same site fetch the
    same pages in the same order — a crawl that varies run to run makes every
    difference in the Brain look like a change in the business.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for url in candidates:
        normalised = url.split("#", 1)[0].rstrip("/") or url
        if normalised in seen or not same_site(normalised, origin):
            continue
        seen.add(normalised)
        kept.append(normalised)

    kept.sort(key=priority_of)
    return kept[:limit]


def links_in(html: str, *, base_url: str) -> list[str]:
    """Internal links, absolute. Used when a sitemap is absent or thin."""
    hrefs = re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return [urljoin(base_url, href) for href in hrefs]


def urls_in_sitemap(xml: str) -> list[str]:
    """`<loc>` entries. Tried before links because a sitemap is the site telling
    us what it considers a page, rather than us guessing from navigation."""
    return [m.strip() for m in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, re.IGNORECASE)]


def looks_javascript_rendered(html: str, extracted_text: str) -> bool:
    """Q51. Thin text while script content dominates.

    Both halves matter. Text alone would flag a genuinely short page — a
    one-line contact page is not a shell. Script volume alone would flag a
    content-rich page that also ships analytics. It is the *combination* that
    means the words are being assembled in a browser we are not running.
    """
    if len(extracted_text.strip()) >= MIN_TEXT_CHARS:
        return False

    script_chars = sum(len(body) for body in _SCRIPT.findall(html))
    text_chars = max(len(extracted_text.strip()), 1)
    return script_chars / text_chars >= SCRIPT_DOMINANCE


JS_RENDERED_MESSAGE: Final = (
    "Your website builds its text in the browser, so there was nothing for us to "
    "read from the page source. Nothing is wrong with the site — we will use your "
    "answers and any documents you upload instead."
)
"""What the founder is told. It says what happened, says the site is fine, and
says what we will do instead — because "we could not read your website" without
those two is a message that reads as an accusation and offers no next step."""
