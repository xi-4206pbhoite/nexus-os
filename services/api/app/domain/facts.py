"""Facts, and the order in which they beat each other.

**`source_kind` *is* the precedence order** (doc 06 §7.4). That is not a
convention layered on top of the enum — it is why the enum is ordered, and the
whole reason a fact carries where it came from.

The order says something specific about trust: a founder who typed a number
beats a connected system, because the system may be misconfigured and the
founder is the authority on their own business. A connected system beats a
crawl, because a live API beats a page that may be a year stale. A crawl beats
an inference, because something we read beats something we guessed. And an
inference beats a document only when nothing better exists — a document is
evidence, but a chunk of one is a sentence out of context.

**A fact never overwrites a fact.** Superseding is a link, not a delete: the
previous value stays, with what replaced it, because "your revenue figure
changed in March" is a question somebody will ask and a row that was updated in
place cannot answer it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class SourceKind(StrEnum):
    """Where a fact came from, in **descending precedence**.

    Declaration order is load-bearing: `PRECEDENCE` is built from it, so adding
    a member in the wrong place silently changes which fact wins. A test asserts
    the order rather than trusting the comment.
    """

    USER_CONFIRMED = "user_confirmed"
    """A person typed it or confirmed it. Beats everything — they are the
    authority on their own business, and a system that disagrees is more likely
    misconfigured than right."""

    CONNECTED_SYSTEM = "connected_system"
    """Read from an API they connected. Live, and not a person's memory."""

    CRAWL = "crawl"
    """Read from their website. Something we read beats something we guessed,
    and it may also be a year out of date."""

    INFERENCE = "inference"
    """Derived by us. Beats a document only because a document chunk is a
    sentence out of context, and this at least considered several."""

    DOCUMENT = "document"
    """Extracted from an uploaded file. Evidence, not testimony."""


PRECEDENCE: Final[tuple[SourceKind, ...]] = tuple(SourceKind)


def rank(kind: SourceKind) -> int:
    """Lower wins. Derived from declaration order, never written out twice."""
    return PRECEDENCE.index(kind)


def wins(candidate: SourceKind, incumbent: SourceKind) -> bool:
    """Whether a new fact should supersede the one already held.

    **Ties do not win.** A second document saying something different from the
    first does not replace it — it is a disagreement, and resolving it by recency
    would mean the last file uploaded quietly rewrites the company's facts. Equal
    precedence goes to the review gate (P13), not to whoever arrived last.
    """
    return rank(candidate) < rank(incumbent)
