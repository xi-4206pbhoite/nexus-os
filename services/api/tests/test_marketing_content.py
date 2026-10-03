"""Generated Marketing content: every claim cited, or not made.

`doc/12` P16 (3.4-3.6). These are the first things in the product where a model
writes something a founder will act on.

A generated plan reads as authority — fluent, structured, specific — and a
founder has no way to tell which sentence came from their own website and which
came from the model's sense of what a growth plan sounds like. That is the
failure these guard against, and it does not look like a failure.
"""

from __future__ import annotations

from app.domain.content import (
    GENERATED,
    BrandVoice,
    Claim,
    keep_grounded,
    voice_violations,
)

HELD = frozenset({"what_you_sell", "ideal_customer"})


def _claim(key: str) -> Claim:
    return Claim(text=f"Something about {key}.", fact_key=key, source_ref=f"onboarding:{key}")


def test_an_unsupported_claim_is_dropped_not_softened() -> None:
    """Rewriting it as "your market may be growing" produces something
    unfalsifiable that still shapes a decision — the hedge reads as caution and
    functions as an assertion."""
    result = keep_grounded(
        [_claim("what_you_sell"), _claim("market_growth_rate")], available_facts=HELD
    )

    assert result is not None
    assert [c.fact_key for c in result.claims] == ["what_you_sell"]
    assert result.dropped == ("market_growth_rate",)


def test_dropped_claims_are_counted_rather_than_discarded_silently() -> None:
    """A plan that quietly lost half its content should look different from one
    that never had it."""
    result = keep_grounded(
        [_claim("what_you_sell"), _claim("a"), _claim("b")], available_facts=HELD
    )
    assert result is not None
    assert len(result.dropped) == 2


def test_nothing_grounded_is_no_plan_rather_than_an_empty_one() -> None:
    """A Growth Plan with no claims is not a short plan; it is the absence of
    one. The caller renders Unavailable rather than a page with headings and
    nothing under them."""
    assert keep_grounded([_claim("unheld")], available_facts=HELD) is None
    assert keep_grounded([], available_facts=HELD) is None


def test_a_claim_cannot_exist_without_a_source_that_opens() -> None:
    """A claim citing a fact key nobody can open is a footnote, not a citation —
    the reader still has to take it on trust, which is what citation removes."""
    import dataclasses

    required = {f.name for f in dataclasses.fields(Claim) if f.default is dataclasses.MISSING}
    assert {"fact_key", "source_ref"} <= required


def test_forbidden_terms_are_checked_after_generation_not_only_requested() -> None:
    """A prompt saying "never say 'synergy'" is a request. This is the check —
    and the point of a forbidden-terms list is that the founder has already been
    embarrassed by one of these words."""
    voice = BrandVoice(forbidden_terms=("synergy", "leverage"))

    assert voice_violations("We will leverage our synergy.", voice) == ("synergy", "leverage")
    assert voice_violations("We will work together.", voice) == ()


def test_a_voice_nobody_stated_is_not_invented() -> None:
    """Inferring a voice from a crawl and writing in it would be the product
    imitating the founder without being asked."""
    assert not BrandVoice().stated
    assert BrandVoice(preferred_terms=("clients",)).stated


def test_the_three_generated_offerings_are_named() -> None:
    assert GENERATED == {"3.4", "3.5", "3.6"}
