"""Proving control of a domain.

Two strong methods and one weak one, per doc 06 §1.1:

| Method | Proves | Strength |
|---|---|---|
| DNS TXT | control of the domain's DNS | strong |
| File at a known path | control of the web server | strong |
| Same-domain email | *employment*, not authority | **weak** |

The weak one is not a lesser version of the strong ones — it answers a different
question. Anyone with a mailbox at a large company can pass it, which is why it
grants workspace creation but flags Owner-claim review when a second person from
the same domain appears.

**The file method is a server-side fetch of a user-supplied domain**, so it goes
through the same SSRF guard as the crawler. Skipping it here because "the user
told us it is their domain" would reopen exactly the hole M2 closed — the claim
is the thing being tested, so it cannot be the reason to trust the target.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import dns.asyncresolver
import dns.exception
import httpx

from app.logging import get_logger
from app.research.ssrf import UrlNotAllowedError, validate_url

log = get_logger(__name__)

# The record and path a claimant publishes.
TXT_PREFIX = "nexus-domain-verification="
WELL_KNOWN_PATH = "/.well-known/nexus-domain-verification.txt"

CHALLENGE_BYTES = 24
FILE_MAX_BYTES = 4096
FILE_TIMEOUT_SECONDS = 10


class Method(StrEnum):
    DNS_TXT = "dns_txt"
    FILE = "file"
    EMAIL = "email"
    MANUAL = "manual"


class Strength(StrEnum):
    STRONG = "strong"
    WEAK = "weak"


STRENGTH_BY_METHOD: dict[Method, Strength] = {
    Method.DNS_TXT: Strength.STRONG,
    Method.FILE: Strength.STRONG,
    # Proves employment, not authority (doc 06 §1.1).
    Method.EMAIL: Strength.WEAK,
    # Support-approved, with documentary evidence. Doc 06 §1.1 names this as
    # the social-engineering target, so it is recorded as weak and logged.
    Method.MANUAL: Strength.WEAK,
}


@dataclass(frozen=True, slots=True)
class CheckResult:
    verified: bool
    evidence: str
    """What was actually observed. Stored, and shown to the claimant on failure."""


def new_challenge() -> str:
    """Random per claim, so proving one domain never helps prove another."""
    return secrets.token_urlsafe(CHALLENGE_BYTES)


def expected_txt_value(challenge: str) -> str:
    return f"{TXT_PREFIX}{challenge}"


def normalise_domain(raw: str) -> str:
    """Reduce a typed value to a bare registrable host.

    Users paste `https://www.acme.om/about?x=1`. Everything after the host is
    irrelevant to ownership, and `www.` is not a different owner.
    """
    value = raw.strip().lower()
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    value = value.split("/")[0].split("?")[0].split("#")[0]
    value = value.split("@")[-1]  # tolerate a pasted email address
    if ":" in value:
        value = value.split(":")[0]
    if value.startswith("www."):
        value = value[4:]
    return value.rstrip(".")


TxtResolver = Callable[[str], list[str]]


async def _resolve_txt(domain: str) -> list[str]:
    try:
        answers = await dns.asyncresolver.resolve(domain, "TXT")
    except (dns.exception.DNSException, ValueError):
        return []
    values: list[str] = []
    for record in answers:
        # A TXT record is a sequence of strings; a long value is split across
        # several, so they are joined before comparison.
        joined = b"".join(record.strings).decode("utf-8", errors="replace")
        values.append(joined)
    return values


async def check_dns_txt(
    domain: str, challenge: str, *, resolve: TxtResolver | None = None
) -> CheckResult:
    """Look for the challenge in the domain's TXT records."""
    expected = expected_txt_value(challenge)
    records = resolve(domain) if resolve else await _resolve_txt(domain)

    if not records:
        return CheckResult(False, "No TXT records found for this domain.")

    for record in records:
        if record.strip() == expected:
            return CheckResult(True, f"TXT record matched on {domain}")

    return CheckResult(
        False,
        f"Found {len(records)} TXT record(s), none matching the challenge.",
    )


async def check_well_known_file(domain: str, challenge: str) -> CheckResult:
    """Look for the challenge in a file at a known path.

    The fetch is SSRF-guarded and the address is pinned, exactly as in the
    crawler. A claim under test is not a reason to trust its target.
    """
    url = f"https://{domain}{WELL_KNOWN_PATH}"
    try:
        target = validate_url(url)
    except UrlNotAllowedError as exc:
        log.info("domain_check.blocked", reason=str(exc))
        return CheckResult(False, "That domain cannot be checked.")

    netloc = f"[{target.ip}]" if ":" in target.ip else target.ip
    by_ip = f"https://{netloc}{WELL_KNOWN_PATH}"

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,  # a redirect could leave the domain entirely
            timeout=httpx.Timeout(FILE_TIMEOUT_SECONDS),
        ) as client:
            response = await client.get(
                by_ip,
                headers={"Host": target.host},
                extensions={"sni_hostname": target.host},
            )
    except httpx.HTTPError:
        return CheckResult(False, f"Could not fetch https://{domain}{WELL_KNOWN_PATH}")

    if response.status_code != 200:
        return CheckResult(False, f"The file returned HTTP {response.status_code}.")

    body = response.content[:FILE_MAX_BYTES].decode("utf-8", errors="replace").strip()
    if body == challenge or body == expected_txt_value(challenge):
        return CheckResult(True, f"File matched at {domain}{WELL_KNOWN_PATH}")

    return CheckResult(False, "The file was found but its contents did not match.")


def email_domain_matches(email: str, domain: str) -> bool:
    """Weak proof: the address is on the domain being claimed.

    Compared against the *normalised* domain, so a subdomain address does not
    silently claim the parent — `x@mail.acme.om` proves `mail.acme.om`.
    """
    if "@" not in email:
        return False
    return normalise_domain(email.split("@")[-1]) == normalise_domain(domain)


# Addresses at these providers prove nothing about a company domain. Doc 06
# §1.1 notes free-email SMEs are common in this market, which is why the manual
# path exists rather than this being a hard block on registration.
FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "mail.com",
        "yandex.com",
        "zoho.com",
        "qq.com",
        "163.com",
    }
)


def is_free_email_domain(domain: str) -> bool:
    return normalise_domain(domain) in FREE_EMAIL_DOMAINS
