"""The review gate: what to show first, and what a founder may accept in bulk.

`doc/12` P13, and three decisions that only look like presentation.

**Impact is how many capabilities depend on the fact** (Q59) — not confidence,
not recency. A founder has finite attention, and ranking by confidence shows
them what we are *least* sure of, which is the opposite of what matters: a
low-confidence fact nothing uses is noise, and a high-confidence fact six
dashboards read is worth ten seconds of their time.

**Bulk-accept only after a theme is expanded** (Q60). An "accept all" button on
a collapsed theme is a button that accepts things nobody has seen — and the
whole purpose of this screen is that a person looked. The rule is cheap to
implement and is the difference between a review and a rubber stamp.

**A deleted fact is not silently re-inferred** (Q62). Deleting says "this is
wrong about my business", and re-deriving it next run tells the founder their
correction did not matter. The deletion is itself a fact about the company.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True, slots=True)
class ReviewFact:
    key: str
    value: str
    source_kind: str
    source_ref: str
    theme: str
    is_assumption: bool
    consumed_by: tuple[str, ...] = ()
    """Capabilities declaring a dependency on this fact. Its length **is** the
    impact score — a fact nothing consumes has no impact, however confident."""

    @property
    def impact(self) -> int:
        return len(self.consumed_by)


@dataclass(slots=True)
class Theme:
    """A group of facts a founder can reason about together."""

    name: str
    facts: list[ReviewFact] = field(default_factory=list)
    expanded: bool = False

    @property
    def may_bulk_accept(self) -> bool:
        """Q60. Only after somebody has actually looked."""
        return self.expanded and bool(self.facts)


MIN_THEMES: Final = 6
MAX_THEMES: Final = 8
TOP_FACTS: Final = 20
"""Six to eight themes, roughly twenty facts (Q59). Not a layout preference: a
review that shows everything is one nobody finishes, and an unfinished review
leaves facts unconfirmed while looking complete."""


def rank(facts: list[ReviewFact]) -> list[ReviewFact]:
    """Highest impact first, then assumptions, then alphabetically.

    Assumptions break the tie because they are the facts the product invented on
    the founder's behalf — of two facts nothing else distinguishes, the one we
    made up deserves their attention more than the one they told us.

    Alphabetical last so the order is **stable**: a review screen that reshuffles
    between visits makes a founder re-read what they already checked.
    """
    return sorted(facts, key=lambda f: (-f.impact, not f.is_assumption, f.key))


def top(facts: list[ReviewFact], limit: int = TOP_FACTS) -> list[ReviewFact]:
    return rank(facts)[:limit]


def assumptions(facts: list[ReviewFact]) -> list[ReviewFact]:
    """The separate block (P13). Kept apart from the ranked list because "we
    guessed this" is a different question from "is this right" — the first asks
    the founder to supply something, the second to check it."""
    return rank([f for f in facts if f.is_assumption])


def into_themes(facts: list[ReviewFact]) -> list[Theme]:
    """Group and order themes by the impact they contain, not by name.

    A theme holding the single most-depended-upon fact in the company belongs at
    the top even if it holds only that one.
    """
    grouped: dict[str, Theme] = {}
    for fact in rank(facts):
        grouped.setdefault(fact.theme, Theme(name=fact.theme)).facts.append(fact)

    return sorted(
        grouped.values(),
        key=lambda t: (-max((f.impact for f in t.facts), default=0), t.name),
    )
