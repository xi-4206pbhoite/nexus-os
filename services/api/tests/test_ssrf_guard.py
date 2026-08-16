"""The SSRF corpus. Written before the crawler it guards (doc 07 §5.3).

Doc 07 M2's acceptance is *"every SSRF test case is blocked"*, so this file is
the specification of that requirement rather than a check on it.

The pre-registration analysis is a **server-side fetch of a URL a stranger
typed**, on an **unauthenticated** endpoint. That is the classic SSRF shape: the
attacker chooses the destination and our server supplies the network position
and the credentials of that position. On a cloud host the prize is the instance
metadata endpoint, which hands out role credentials to anything that can make a
plain HTTP request from the instance.

Doc 06 §1.2 also requires this guard to apply to **discovered competitor URLs**,
which are influenced by search results and by the model — and are therefore not
trusted input either.

Resolution is injected so these tests never touch the network. A guard tested
against live DNS would be a guard tested against whatever DNS happened to say.
"""

from __future__ import annotations

import pytest

from app.connectors.ssrf import (
    UrlNotAllowedError,
    is_public_ip,
    validate_url,
)


def resolver_returning(*ips: str):  # type: ignore[no-untyped-def]
    def _resolve(host: str) -> list[str]:
        return list(ips)

    return _resolve


PUBLIC = resolver_returning("93.184.216.34")


# ── Scheme ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://C:/Windows/win.ini",
        "gopher://127.0.0.1:6379/_SET%20key%20value",
        "ftp://internal.example.com/",
        "dict://127.0.0.1:11211/stat",
        "ldap://127.0.0.1/",
        "jar:http://example.com!/",
        "data:text/html,<script>alert(1)</script>",
        "javascript:alert(1)",
        "redis://127.0.0.1:6379",
    ],
)
def test_non_http_schemes_are_blocked(url: str) -> None:
    """gopher and dict in particular can drive plaintext protocols like Redis."""
    with pytest.raises(UrlNotAllowedError):
        validate_url(url, resolve=PUBLIC)


@pytest.mark.parametrize("url", ["http://example.com/", "https://example.com/"])
def test_http_and_https_are_allowed(url: str) -> None:
    assert validate_url(url, resolve=PUBLIC).scheme in {"http", "https"}


# ── Loopback, private and link-local ──────────────────────────


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1", "127.1.1.1", "0.0.0.0",  # loopback / unspecified
        "10.0.0.5", "10.255.255.255",          # RFC1918
        "172.16.0.1", "172.31.255.254",
        "192.168.1.1",
        "169.254.169.254",                      # cloud metadata
        "169.254.0.1",                          # link-local
        "100.64.0.1",                           # carrier-grade NAT
        "192.0.0.1",                            # IETF protocol assignments
        "198.18.0.1",                           # benchmarking
        "224.0.0.1",                            # multicast
        "255.255.255.255",                      # broadcast
    ],
)
def test_private_and_reserved_ipv4_are_not_public(ip: str) -> None:
    assert is_public_ip(ip) is False


@pytest.mark.parametrize(
    "ip",
    [
        "::1",                    # loopback
        "fe80::1",                # link-local
        "fc00::1", "fd00::1",     # unique local
        "::ffff:127.0.0.1",       # IPv4-mapped loopback
        "::ffff:169.254.169.254", # IPv4-mapped metadata
        "::",                     # unspecified
    ],
)
def test_private_and_reserved_ipv6_are_not_public(ip: str) -> None:
    """IPv4-mapped forms are the ones people forget."""
    assert is_public_ip(ip) is False


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"])
def test_genuinely_public_addresses_are_public(ip: str) -> None:
    assert is_public_ip(ip) is True


# ── Hostnames resolving somewhere they should not ─────────────


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "169.254.169.254", "10.0.0.1", "192.168.0.1", "::1"],
)
def test_public_hostname_resolving_to_a_private_address_is_blocked(ip: str) -> None:
    """The name means nothing; only the resolved address does.

    `internal.evil.com` is a perfectly ordinary public name that an attacker
    controls and points at 169.254.169.254.
    """
    with pytest.raises(UrlNotAllowedError):
        validate_url("https://internal.evil.com/", resolve=resolver_returning(ip))


def test_any_private_answer_blocks_even_when_a_public_one_exists() -> None:
    """A DNS answer with mixed records must not be cherry-picked.

    Accepting it because *one* record is public leaves the connection free to
    use the private one — and makes the outcome depend on resolver ordering.
    """
    with pytest.raises(UrlNotAllowedError):
        validate_url(
            "https://mixed.evil.com/",
            resolve=resolver_returning("93.184.216.34", "169.254.169.254"),
        )


def test_host_with_no_dns_answer_is_blocked() -> None:
    with pytest.raises(UrlNotAllowedError):
        validate_url("https://nowhere.example/", resolve=resolver_returning())


# ── Literal and obfuscated addresses ──────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:169.254.169.254]/",
        "http://0177.0.0.1/",        # octal
        "http://2130706433/",        # decimal
        "http://0x7f.0x0.0x0.0x1/",  # hex
    ],
)
def test_literal_and_encoded_loopback_forms_are_blocked(url: str) -> None:
    """Octal, decimal and hex forms all resolve to 127.0.0.1 in many stacks."""
    with pytest.raises(UrlNotAllowedError):
        validate_url(url, resolve=PUBLIC)


@pytest.mark.parametrize(
    "url",
    [
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://metadata/computeMetadata/v1/",
        "http://instance-data/latest/meta-data/",
    ],
)
def test_known_metadata_hostnames_are_blocked_by_name(url: str) -> None:
    """Blocked by name as well as by address.

    Belt and braces: if a resolver is ever misconfigured, or a future code path
    skips resolution, the name alone must still be refused.
    """
    with pytest.raises(UrlNotAllowedError):
        validate_url(url, resolve=PUBLIC)


# ── Credentials, ports and shape ──────────────────────────────


def test_userinfo_in_the_url_is_blocked() -> None:
    """`http://expected.com@evil.com/` reads as one host and connects to another."""
    with pytest.raises(UrlNotAllowedError):
        validate_url("http://user:pass@example.com/", resolve=PUBLIC)


@pytest.mark.parametrize("port", [22, 25, 3306, 5432, 6379, 11211, 9200])
def test_non_web_ports_are_blocked(port: int) -> None:
    """An HTTP request to Redis or Postgres is still a request they may act on."""
    with pytest.raises(UrlNotAllowedError):
        validate_url(f"http://example.com:{port}/", resolve=PUBLIC)


@pytest.mark.parametrize("port", [80, 443, 8080, 8443])
def test_web_ports_are_allowed(port: int) -> None:
    assert validate_url(f"http://example.com:{port}/", resolve=PUBLIC).port == port


@pytest.mark.parametrize(
    "url",
    ["", "   ", "notaurl", "http://", "https:///path", "http://:80/", "http://[/"],
)
def test_malformed_urls_are_blocked(url: str) -> None:
    with pytest.raises(UrlNotAllowedError):
        validate_url(url, resolve=PUBLIC)


def test_absurdly_long_url_is_blocked() -> None:
    with pytest.raises(UrlNotAllowedError):
        validate_url("https://example.com/" + "a" * 10_000, resolve=PUBLIC)


# ── The IP is pinned, so DNS cannot be rebound ────────────────


def test_validation_pins_the_resolved_address() -> None:
    """Returning the validated IP is what closes the TOCTOU window.

    Validate-then-connect-by-name resolves twice: once for the check and once
    for the connection. An attacker's DNS can answer publicly the first time and
    privately the second. The connection must therefore be made to the address
    that was actually validated.
    """
    target = validate_url("https://example.com/path", resolve=resolver_returning("93.184.216.34"))
    assert target.ip == "93.184.216.34"
    assert target.host == "example.com"


def test_pinned_address_is_one_of_the_resolved_answers() -> None:
    target = validate_url("https://example.com/", resolve=resolver_returning("8.8.8.8"))
    assert target.ip == "8.8.8.8"


# ── Redirects are re-validated per hop (doc 06 §1.2) ──────────


def test_redirect_target_is_validated_the_same_way() -> None:
    """A public page that 302s to the metadata endpoint is the standard bypass.

    Validating only the first URL is the single most common way this guard is
    got wrong, so the redirect path uses the same function rather than a
    lighter-weight check.
    """
    with pytest.raises(UrlNotAllowedError):
        validate_url("http://169.254.169.254/", resolve=PUBLIC)


def test_relative_redirects_resolve_against_the_previous_hop() -> None:
    from app.connectors.ssrf import resolve_redirect

    assert (
        resolve_redirect("https://example.com/a/b", "../c") == "https://example.com/c"
    )
    assert resolve_redirect("https://example.com/a/b", "/d") == "https://example.com/d"


def test_redirect_to_a_new_scheme_is_still_checked() -> None:
    from app.connectors.ssrf import resolve_redirect

    target = resolve_redirect("https://example.com/", "file:///etc/passwd")
    with pytest.raises(UrlNotAllowedError):
        validate_url(target, resolve=PUBLIC)
