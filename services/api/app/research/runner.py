"""Running the crawl source: seed, discover, fetch, record.

Joins three things that already exist and adds no new judgement of its own.
`fetch_page` fetches one page with the SSRF guard re-applied at every redirect
hop; `site.plan` decides which twenty pages are worth the budget; `site.Budget`
decides when to stop. **None of that is reimplemented here** — a second copy of
the guard is the one thing this module must never grow.

The shape it does own is Q56's: **this returns an outcome, it never raises past
its own boundary.** A crawl that fails must leave the other five sources of the
run untouched, so every failure inside becomes a `SourceState` and a sentence,
and the caller writes it beside whatever the others produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from app.domain.research import SourceState
from app.logging import get_logger
from app.research import site
from app.research.crawler import FetchError, fetch_page
from app.research.extract import extract_text

log = get_logger(__name__)

MAX_BYTES: Final = 2 * 1024 * 1024
PAGE_TIMEOUT_SECONDS: Final = 15
MAX_REDIRECTS: Final = 5


@dataclass(slots=True)
class CrawlOutcome:
    """What the crawl produced, and what to write to `research_source`."""

    state: SourceState
    error_reason: str = ""
    pages: list[dict[str, str]] = field(default_factory=list)
    js_rendered_urls: list[str] = field(default_factory=list)


async def _fetch(url: str) -> tuple[str, str] | None:
    """One page's html and text, or `None` if it could not be read.

    Swallows `FetchError` deliberately: one unreachable page out of twenty is
    not a failed crawl. A 404 on `/pricing` means they have no pricing page,
    which is a fact about the company rather than an error in our reading.
    """
    try:
        page = await fetch_page(
            url,
            max_bytes=MAX_BYTES,
            timeout_seconds=PAGE_TIMEOUT_SECONDS,
            max_redirects=MAX_REDIRECTS,
        )
    except FetchError as exc:
        log.info("crawl.page_skipped", reason=str(exc))
        return None
    return page.html, extract_text(page.html)


async def crawl_site(seeds: list[str], *, elapsed: float = 0.0) -> CrawlOutcome:
    """Crawl a company's site and report what happened.

    **Returns rather than raises**, including when everything fails. Q56: one
    source failing must never fail the run, and a function that raises makes
    that the caller's problem to remember — which is the kind of rule that holds
    until somebody adds a second caller.
    """
    if not seeds:
        return CrawlOutcome(
            state=SourceState.SKIPPED,
            error_reason="",
        )

    origin = seeds[0]
    outcome = CrawlOutcome(state=SourceState.RUNNING)
    budget = site.Budget(pages_fetched=0, elapsed_seconds=elapsed)

    # The sitemap first: it is the site telling us what it considers a page,
    # rather than us inferring it from navigation. Failure here is ordinary —
    # most small-business sites do not have one.
    discovered = list(seeds)
    sitemap = await _fetch(f"{origin.rstrip('/')}/sitemap.xml")
    if sitemap is not None:
        discovered.extend(site.urls_in_sitemap(sitemap[0]))

    targets = site.plan(discovered, origin=origin)
    shells = 0

    for url in targets:
        if budget.exhausted:
            log.info("crawl.budget_spent", pages=budget.pages_fetched)
            break

        fetched = await _fetch(url)
        budget = site.Budget(
            pages_fetched=budget.pages_fetched + 1, elapsed_seconds=budget.elapsed_seconds
        )
        if fetched is None:
            continue

        html, text = fetched
        if site.looks_javascript_rendered(html, text):
            shells += 1
            outcome.js_rendered_urls.append(url)
            continue

        outcome.pages.append({"url": url, "text": text})

        # Links are a fallback, not a second pass: they extend the plan only
        # while there is budget left to use them.
        if len(targets) < site.MAX_PAGES:
            targets = site.plan(targets + site.links_in(html, base_url=url), origin=origin)

    if outcome.pages:
        outcome.state = SourceState.SUCCEEDED
        return outcome

    if shells:
        # Q51. The site is not broken and must not be told it is.
        outcome.state = SourceState.JS_RENDERED
        return outcome

    outcome.state = SourceState.FAILED
    outcome.error_reason = (
        "We could not read any pages on your website. It may be temporarily "
        "unreachable — your answers and any documents you upload are used either way."
    )
    return outcome
