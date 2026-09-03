"""Redirect handling in the crawler.

`test_ssrf_guard.py` proves `validate_url` and `resolve_redirect` behave, but it
proves it about those functions in isolation. The failure this file exists to
catch is a *wiring* failure: a crawler that validates the URL it was handed and
then lets the HTTP client follow redirects on its own. Every unit test still
passes, and a public URL that 302s to `169.254.169.254` gets fetched anyway.

That is the most common way an SSRF guard is defeated in practice, so it earns an
end-to-end test through `fetch_page` rather than a unit test of the parts.

The transport is mocked and DNS is scripted. Both have to be: there is no way to
exercise "a public host redirects to a private address" against the real network
without owning a hostile nameserver.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.research import crawler
from app.research import ssrf as ssrf_module
from app.research.crawler import FetchError, fetch_page

PUBLIC_A = "93.184.216.34"
PUBLIC_B = "93.184.216.35"

HTML = b"<html><head><title>Landed</title></head><body>ok</body></html>"

Handler = Callable[[httpx.Request], httpx.Response]
DnsSetter = Callable[[dict[str, list[str]]], None]


@pytest.fixture
def dns(monkeypatch: pytest.MonkeyPatch) -> DnsSetter:
    """Script DNS. Anything not in the mapping does not resolve."""

    def set_map(mapping: dict[str, list[str]]) -> None:
        monkeypatch.setattr(
            ssrf_module,
            "_system_resolver",
            lambda host: list(mapping.get(host.lower(), [])),
        )

    return set_map


@pytest.fixture
def seen() -> list[httpx.Request]:
    """Every request that reached the transport, in order."""
    return []


@pytest.fixture
def transport(
    monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request]
) -> Callable[[Handler], None]:
    """Route the crawler's client through a mock transport, recording requests."""

    def install(handler: Handler) -> None:
        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        def fake_client(timeout: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.MockTransport(recording),
                follow_redirects=False,
                timeout=httpx.Timeout(timeout),
                headers={"User-Agent": crawler.USER_AGENT},
            )

        monkeypatch.setattr(crawler, "_client", fake_client)

    return install


def redirect_to(location: str, status_code: int = 302) -> httpx.Response:
    return httpx.Response(status_code, headers={"location": location})


def landing_page() -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html"}, content=HTML)


async def crawl(
    url: str, *, max_redirects: int = 5, max_bytes: int = 1_000_000
) -> crawler.FetchedPage:
    return await fetch_page(
        url, max_bytes=max_bytes, timeout_seconds=5, max_redirects=max_redirects
    )


# ── The attack this file is named for ─────────────────────────


@pytest.mark.parametrize(
    "private_target",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://2130706433/",
        "http://metadata.google.internal/",
        "http://100.64.0.1/",
    ],
)
async def test_a_public_url_redirecting_to_a_private_one_is_refused(
    private_target: str,
    dns: DnsSetter,
    transport: Callable[[Handler], None],
    seen: list[httpx.Request],
) -> None:
    """Hop one is a genuine public site. Hop two is not, and must never be
    fetched — the guard has to run *after* the redirect, not only before it."""
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: redirect_to(private_target))

    with pytest.raises(FetchError) as exc:
        await crawl("https://public.example/")

    assert exc.value.blocked is True, "must be attributed to the guard, not the network"
    # The reason is safe to show: it cannot confirm internal network shape to
    # whoever supplied the URL.
    assert "169.254" not in exc.value.reason
    assert "127.0.0.1" not in exc.value.reason
    assert len(seen) == 1, "the redirect was refused before it was followed"


async def test_a_redirect_to_a_non_web_scheme_is_refused(
    dns: DnsSetter, transport: Callable[[Handler], None], seen: list[httpx.Request]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: redirect_to("file:///etc/passwd"))

    with pytest.raises(FetchError) as exc:
        await crawl("https://public.example/")

    assert exc.value.blocked is True
    assert len(seen) == 1


async def test_a_redirect_to_a_non_web_port_is_refused(
    dns: DnsSetter, transport: Callable[[Handler], None], seen: list[httpx.Request]
) -> None:
    """Ports are an allowlist, so a redirect to Redis or Postgres is refused by
    the same rule that refuses anything that is not a website."""
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: redirect_to("http://public.example:6379/"))

    with pytest.raises(FetchError) as exc:
        await crawl("https://public.example/")

    assert exc.value.blocked is True
    assert len(seen) == 1


async def test_a_relative_redirect_is_resolved_then_validated(
    dns: DnsSetter, transport: Callable[[Handler], None], seen: list[httpx.Request]
) -> None:
    """A bare `Location: /home` must be absolutised against the hop it came from
    and re-checked — not treated as uncheckable and waved through."""
    dns({"public.example": [PUBLIC_A]})
    transport(lambda request: redirect_to("/home") if request.url.path == "/" else landing_page())

    result = await crawl("https://public.example/")

    assert result.final_url == "https://public.example/home"
    assert result.redirect_chain == ("https://public.example/",)
    assert len(seen) == 2


# ── The guard must not block legitimate redirects ─────────────


async def test_a_redirect_between_public_hosts_is_followed(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    """The ordinary real case — an apex to www, or `acme.om` to `acme.om/en/`.
    A guard that refused these would be useless in production, so the happy path
    is asserted alongside the blocks."""
    dns({"public.example": [PUBLIC_A], "www.public.example": [PUBLIC_B]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("host") == "public.example":
            return redirect_to("https://www.public.example/en/", status_code=301)
        return landing_page()

    transport(handler)
    result = await crawl("https://public.example/")

    assert result.final_url == "https://www.public.example/en/"
    assert "Landed" in result.html


async def test_every_hop_connects_by_pinned_ip_with_the_host_header_intact(
    dns: DnsSetter, transport: Callable[[Handler], None], seen: list[httpx.Request]
) -> None:
    """The DNS-rebinding defence, asserted on the wire rather than by reading it.

    Validating a name and then connecting to that name resolves DNS twice, and an
    attacker's nameserver may answer publicly the first time and privately the
    second. Every hop must connect to the address that was validated, carrying
    the original host in the header so virtual hosting and certificates work.
    """
    dns({"public.example": [PUBLIC_A], "www.public.example": [PUBLIC_B]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("host") == "public.example":
            return redirect_to("https://www.public.example/en/")
        return landing_page()

    transport(handler)
    await crawl("https://public.example/")

    assert [str(r.url.host) for r in seen] == [PUBLIC_A, PUBLIC_B]
    assert [r.headers["host"] for r in seen] == ["public.example", "www.public.example"]


# ── Caps ──────────────────────────────────────────────────────


async def test_a_redirect_loop_is_bounded(
    dns: DnsSetter, transport: Callable[[Handler], None], seen: list[httpx.Request]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: redirect_to("https://public.example/"))

    with pytest.raises(FetchError) as exc:
        await crawl("https://public.example/", max_redirects=3)

    assert "redirected too many times" in exc.value.reason
    assert len(seen) == 4, "bounded by max_redirects + 1, not by the loop terminating"


async def test_a_redirect_without_a_destination_is_an_error(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(lambda _request: httpx.Response(302))

    with pytest.raises(FetchError) as exc:
        await crawl("https://public.example/")

    assert "without a destination" in exc.value.reason


async def test_an_oversized_body_is_capped_on_bytes_actually_read(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    """`Content-Length` is supplied by the server being fetched, so a hostile one
    can understate it. The cap has to be enforced on what was read."""
    dns({"public.example": [PUBLIC_A]})
    body = b"<html><body>" + (b"x" * 50_000) + b"</body></html>"
    transport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "10"},
            content=body,
        )
    )

    result = await crawl("https://public.example/", max_bytes=1_000)

    assert result.truncated is True
    assert len(result.html) <= 1_000


async def test_a_non_html_response_is_refused(
    dns: DnsSetter, transport: Callable[[Handler], None]
) -> None:
    dns({"public.example": [PUBLIC_A]})
    transport(
        lambda _request: httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4"
        )
    )

    with pytest.raises(FetchError) as exc:
        await crawl("https://public.example/")

    assert "not a web page" in exc.value.reason
    assert exc.value.blocked is False, "a wrong content type is not an SSRF block"


async def test_a_host_that_does_not_resolve_is_refused(
    dns: DnsSetter, transport: Callable[[Handler], None], seen: list[httpx.Request]
) -> None:
    dns({})
    transport(lambda _request: landing_page())

    with pytest.raises(FetchError) as exc:
        await crawl("https://nowhere.example/")

    assert exc.value.blocked is True
    assert seen == [], "nothing should have been dialled"
