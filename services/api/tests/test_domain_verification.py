"""Proving control of a domain.

Doc 07 M3's acceptance is *"no workspace exists without a verified domain"*, and
its validation step is *"try to create a workspace for a domain I don't control
and fail"*. So the cases that matter are the ones where verification should
**not** pass.

Doc 06 §1.1 is blunt about why: without this check NEXUS crawls a company the
registrant does not own, names its competitors, and hands that to a stranger.
"""

from __future__ import annotations

import pytest

from app.connectors.domain_check import (
    FREE_EMAIL_DOMAINS,
    STRENGTH_BY_METHOD,
    Method,
    Strength,
    check_dns_txt,
    email_domain_matches,
    expected_txt_value,
    is_free_email_domain,
    new_challenge,
    normalise_domain,
)

DOMAIN = "acme.om"


def resolver_returning(*records: str):  # type: ignore[no-untyped-def]
    def _resolve(domain: str) -> list[str]:
        return list(records)

    return _resolve


# ── Challenges ────────────────────────────────────────────────


def test_challenges_are_unique() -> None:
    """A predictable challenge is no challenge at all."""
    assert len({new_challenge() for _ in range(200)}) == 200


def test_challenge_has_meaningful_entropy() -> None:
    assert len(new_challenge()) >= 30


# ── DNS TXT ───────────────────────────────────────────────────


async def test_matching_txt_record_verifies() -> None:
    challenge = new_challenge()
    result = await check_dns_txt(
        DOMAIN, challenge, resolve=resolver_returning(expected_txt_value(challenge))
    )
    assert result.verified is True
    assert DOMAIN in result.evidence


async def test_absent_txt_record_does_not_verify() -> None:
    result = await check_dns_txt(DOMAIN, new_challenge(), resolve=resolver_returning())
    assert result.verified is False
    assert "No TXT records" in result.evidence


async def test_a_different_challenge_does_not_verify() -> None:
    """The whole point: publishing *something* is not publishing *this*."""
    mine, theirs = new_challenge(), new_challenge()
    result = await check_dns_txt(
        DOMAIN, mine, resolve=resolver_returning(expected_txt_value(theirs))
    )
    assert result.verified is False


async def test_unrelated_txt_records_do_not_verify() -> None:
    """Most domains already have SPF and site-verification records."""
    result = await check_dns_txt(
        DOMAIN,
        new_challenge(),
        resolve=resolver_returning(
            "v=spf1 include:_spf.google.com ~all",
            "google-site-verification=abc123",
        ),
    )
    assert result.verified is False
    assert "none matching" in result.evidence


async def test_the_correct_record_is_found_among_others() -> None:
    challenge = new_challenge()
    result = await check_dns_txt(
        DOMAIN,
        challenge,
        resolve=resolver_returning(
            "v=spf1 -all",
            expected_txt_value(challenge),
            "google-site-verification=xyz",
        ),
    )
    assert result.verified is True


async def test_the_prefix_is_required() -> None:
    """A bare token in a TXT record is not the agreed record.

    Requiring the prefix keeps the check unambiguous when a domain publishes
    many verification records from different vendors.
    """
    challenge = new_challenge()
    result = await check_dns_txt(DOMAIN, challenge, resolve=resolver_returning(challenge))
    assert result.verified is False


async def test_surrounding_whitespace_is_tolerated() -> None:
    """DNS providers vary in how they store the value; the user did their part."""
    challenge = new_challenge()
    result = await check_dns_txt(
        DOMAIN, challenge, resolve=resolver_returning(f"  {expected_txt_value(challenge)}  ")
    )
    assert result.verified is True


# ── Strength is a stored fact ─────────────────────────────────


def test_dns_and_file_are_strong_and_email_is_not() -> None:
    """These prove different things, so they are not graded on one axis.

    DNS and file prove control of the domain. An email address on the domain
    proves employment — anyone with a mailbox at a large company passes it.
    """
    assert STRENGTH_BY_METHOD[Method.DNS_TXT] is Strength.STRONG
    assert STRENGTH_BY_METHOD[Method.FILE] is Strength.STRONG
    assert STRENGTH_BY_METHOD[Method.EMAIL] is Strength.WEAK


def test_manual_approval_is_weak() -> None:
    """Doc 06 §1.1 names it the social-engineering target."""
    assert STRENGTH_BY_METHOD[Method.MANUAL] is Strength.WEAK


def test_every_method_has_a_strength() -> None:
    for method in Method:
        assert method in STRENGTH_BY_METHOD


# ── Domain normalisation ──────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("acme.om", "acme.om"),
        ("ACME.OM", "acme.om"),
        ("https://acme.om", "acme.om"),
        ("http://acme.om/", "acme.om"),
        ("https://www.acme.om/about?x=1", "acme.om"),
        ("www.acme.om", "acme.om"),
        ("acme.om.", "acme.om"),
        ("acme.om:443", "acme.om"),
        ("  acme.om  ", "acme.om"),
        ("someone@acme.om", "acme.om"),
    ],
)
def test_domain_normalisation(raw: str, expected: str) -> None:
    assert normalise_domain(raw) == expected


def test_a_subdomain_is_not_the_parent() -> None:
    """Normalising `mail.acme.om` to `acme.om` would let a subdomain owner
    claim the parent company."""
    assert normalise_domain("mail.acme.om") == "mail.acme.om"
    assert normalise_domain("mail.acme.om") != "acme.om"


# ── Email as weak proof ───────────────────────────────────────


def test_matching_email_domain_passes() -> None:
    assert email_domain_matches("parul@acme.om", "acme.om") is True
    assert email_domain_matches("Parul@ACME.OM", "https://www.acme.om") is True


def test_different_email_domain_fails() -> None:
    assert email_domain_matches("parul@evil.com", "acme.om") is False


def test_subdomain_email_does_not_prove_the_parent() -> None:
    """`x@mail.acme.om` proves `mail.acme.om`, not `acme.om`."""
    assert email_domain_matches("x@mail.acme.om", "acme.om") is False


def test_lookalike_domain_fails() -> None:
    """Suffix matching would accept `acme.om.evil.com`."""
    assert email_domain_matches("x@acme.om.evil.com", "acme.om") is False
    assert email_domain_matches("x@notacme.om", "acme.om") is False


def test_malformed_email_fails() -> None:
    assert email_domain_matches("not-an-email", "acme.om") is False
    assert email_domain_matches("", "acme.om") is False


# ── Free email providers ──────────────────────────────────────


@pytest.mark.parametrize("domain", sorted(FREE_EMAIL_DOMAINS)[:8])
def test_free_providers_are_recognised(domain: str) -> None:
    """A gmail address proves nothing about a company domain."""
    assert is_free_email_domain(domain) is True


def test_a_company_domain_is_not_a_free_provider() -> None:
    assert is_free_email_domain("acme.om") is False


def test_free_provider_check_normalises() -> None:
    assert is_free_email_domain("GMAIL.COM") is True
    assert is_free_email_domain("https://gmail.com") is True
