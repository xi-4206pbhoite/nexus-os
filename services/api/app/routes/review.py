"""The review gate, over HTTP.

The rules live in `app/domain/review_gate.py` and are tested there. This route
reads facts, applies them, and returns a screen's worth — it makes **no
decisions of its own**, which is the same arrangement the dashboards use and for
the same reason: a route that ranks differently from the domain is a second
opinion nobody knows exists.

**Unreviewed facts are returned, labelled.** `doc/12` P13: they are usable and
marked `inferred` wherever they appear. Withholding them until review would make
the product useless until somebody finished a screen, and hiding the label would
make a guess look like a fact.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.deps import CurrentScope
from app.domain.review_gate import ReviewFact, assumptions, into_themes, top
from app.logging import get_logger
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/review", tags=["review"])
log = get_logger(__name__)


class FactOut(BaseModel):
    key: str
    value: str
    source_kind: str
    source_ref: str
    """Precise enough to open. A fact whose source cannot be opened is a fact
    nobody can check."""

    impact: int
    is_assumption: bool
    confirmed: bool
    label: str
    """`confirmed` or `inferred`. Returned rather than derived by the client:
    an unreviewed fact shown without its label is a guess wearing a fact's
    clothes, and that is the one thing this product must never do."""


class ThemeOut(BaseModel):
    name: str
    facts: list[FactOut]
    may_bulk_accept: bool
    """Always `false` here. Q60: bulk-accept unlocks only once the founder has
    expanded the theme, which is state the client holds — the server states the
    rule's starting position rather than pretending to know."""


class ReviewOut(BaseModel):
    themes: list[ThemeOut]
    highest_impact: list[FactOut]
    assumptions: list[FactOut]
    total_facts: int


def _out(fact: ReviewFact, *, confirmed: bool) -> FactOut:
    return FactOut(
        key=fact.key,
        value=fact.value,
        source_kind=fact.source_kind,
        source_ref=fact.source_ref,
        impact=fact.impact,
        is_assumption=fact.is_assumption,
        confirmed=confirmed,
        label="confirmed" if confirmed else "inferred",
    )


@router.get("", response_model=ReviewOut)
async def read_review(scope: CurrentScope) -> ReviewOut:
    """Everything the review screen needs, ranked by the domain's rules."""
    async with scoped_connection(scope) as db:
        rows = (
            await db.execute(
                text(
                    "SELECT f.key, f.value, f.source_kind, f.source_ref,"
                    "       f.confirmed_at IS NOT NULL AS confirmed"
                    "  FROM fact f"
                    "  JOIN brain_version b ON b.id = f.brain_version_id"
                    " WHERE f.superseded_by_id IS NULL"
                    " ORDER BY b.version DESC, f.key"
                )
            )
        ).all()

    confirmed_by_key = {row.key: row.confirmed for row in rows}
    facts = [
        ReviewFact(
            key=row.key,
            value=row.value,
            source_kind=row.source_kind,
            source_ref=row.source_ref,
            # A theme per source kind until capability metadata carries one.
            # Named after where the fact came from, which is at least a grouping
            # a founder can reason about, rather than a bucket called "other".
            theme=row.source_kind.replace("_", " "),
            is_assumption=row.source_kind == "inference",
        )
        for row in rows
    ]

    return ReviewOut(
        themes=[
            ThemeOut(
                name=theme.name,
                facts=[_out(f, confirmed=confirmed_by_key.get(f.key, False)) for f in theme.facts],
                may_bulk_accept=theme.may_bulk_accept,
            )
            for theme in into_themes(facts)
        ],
        highest_impact=[_out(f, confirmed=confirmed_by_key.get(f.key, False)) for f in top(facts)],
        assumptions=[
            _out(f, confirmed=confirmed_by_key.get(f.key, False)) for f in assumptions(facts)
        ],
        total_facts=len(facts),
    )
