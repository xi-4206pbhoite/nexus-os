"""Marketing's generated capabilities: Growth Plan, calendar, Content Studio.

`doc/12` P16 (3.4, 3.5, 3.6). These are the first things in the product where a
model writes something a founder will act on, so they are the first place P14's
pipeline stops being a precaution.

**Every claim is cited or it is not made.** A generated plan reads as authority:
it is fluent, structured, and specific, and a founder has no way to tell which
sentence came from their own website and which came from the model's sense of
what a growth plan sounds like. So a claim carries the fact it rests on, and one
that cannot is dropped — not softened, dropped. Softening produces "your market
may be growing", which is unfalsifiable and still shapes a decision.

**Brand voice comes from facts, not from taste.** `preferred_terms` and
`forbidden_terms` are things the founder told us or we read from their site.
Inferring a voice from a crawl and then writing in it would be the product
imitating them without being asked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

GROWTH_PLAN: Final = "3.4"
CALENDAR: Final = "3.5"
CONTENT_STUDIO: Final = "3.6"

GENERATED: Final[frozenset[str]] = frozenset({GROWTH_PLAN, CALENDAR, CONTENT_STUDIO})


@dataclass(frozen=True, slots=True)
class Claim:
    """One sentence and the fact it rests on.

    `fact_key` and `source_ref` are both required. A claim citing a fact key
    nobody can open is a footnote rather than a citation — the reader has to
    take it on trust, which is the thing citation exists to remove.
    """

    text: str
    fact_key: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class BrandVoice:
    """What the founder said about how they sound. Never inferred."""

    preferred_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()

    @property
    def stated(self) -> bool:
        return bool(self.preferred_terms or self.forbidden_terms)


@dataclass(frozen=True, slots=True)
class Generated:
    """A generated artefact and what it stands on."""

    offering_id: str
    claims: tuple[Claim, ...] = field(default=())
    dropped: tuple[str, ...] = field(default=())
    """Claims removed for having no fact behind them. Counted and reported
    rather than discarded silently — a plan that quietly lost half its content
    should look different from one that never had it."""

    @property
    def grounded(self) -> bool:
        return bool(self.claims)


def keep_grounded(candidates: list[Claim], *, available_facts: frozenset[str]) -> Generated | None:
    """Drop every claim whose fact we do not hold. Returns `None` if none survive.

    **Dropped, not softened.** Rewriting an unsupported claim as "your market may
    be growing" produces something unfalsifiable that still shapes a decision —
    the hedge reads as caution and functions as an assertion.

    `None` rather than an empty plan, because a Growth Plan with no claims is
    not a short plan; it is the absence of one, and the caller must render it as
    Unavailable rather than as a page with headings and nothing under them.
    """
    kept = tuple(c for c in candidates if c.fact_key in available_facts)
    dropped = tuple(c.fact_key for c in candidates if c.fact_key not in available_facts)

    if not kept:
        return None

    return Generated(offering_id=GROWTH_PLAN, claims=kept, dropped=dropped)


def voice_violations(text: str, voice: BrandVoice) -> tuple[str, ...]:
    """Forbidden terms that appear anyway.

    Checked after generation rather than only instructed before it. A prompt
    saying "never say 'synergy'" is a request; this is the check — and the whole
    point of a forbidden-terms list is that the founder has already been
    embarrassed by one of these words.
    """
    lowered = text.lower()
    return tuple(term for term in voice.forbidden_terms if term.lower() in lowered)
