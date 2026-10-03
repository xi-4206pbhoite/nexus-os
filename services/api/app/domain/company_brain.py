"""Assembling the company brain from what the founder actually told us.

**This is not generation, and the distinction is the product.** By the end of
onboarding the founder has typed what they sell, who they sell it to, what they
are trying to do, and how each of their departments works — every answer still
carrying the question it answers. Putting that together invents nothing and can
name a source for every line, which is I1 exactly.

So a workspace with no language model gets a **real** brain, not an apology.
The model's job when it arrives is to *enrich* this — better prose, contradictions
spotted against uploaded documents — not to be the only way to have one at all.

Three rules the assembly follows, each of which the schema also enforces:

- **Every claim carries its source.** `provenance` names the question key each
  line came from. A brain that cannot say where a claim came from is the thing
  this product exists not to be, so `ck_company_brain_grounded_has_provenance`
  refuses a grounded brain with an empty list.
- **An assumption is never quietly a fact.** "Not sure yet" stored the
  question's stated assumption flagged as one (`is_assumption`), and it travels
  into `assumptions` rather than into the prose. A document may contradict it
  later, and that is the point of keeping the two apart.
- **A proposal is not an answer.** A Contributor's department answer is
  `proposed` until a manager confirms it, so it is excluded — the review gate
  exists precisely to stop unconfirmed claims becoming company facts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.onboarding import BY_KEY

# The company-stage keys that become prose, and the field each one feeds.
# Explicit rather than inferred: a question silently changing which part of the
# brain it writes to is a change nobody would see until the brain read wrong.
FIELD_FOR_KEY: Final[dict[str, str]] = {
    "what_you_sell": "products_services",
    "ideal_customer": "target_customers",
    "top_goals": "goals",
    "biggest_challenges": "goals",
}


class GeneratedBy(StrEnum):
    """How the brain came to exist, in `ck_company_brain_generated_by`'s own
    vocabulary.

    An enum rather than three string literals because
    `tests/test_constraint_enum_parity.py` insists on it — and it insists
    because `ck_chunk_review_state` once permitted four values while the code
    wrote a different four, and nothing could see the drift: the enum
    type-checked, the constraint was valid SQL, and the only place they met was
    an INSERT no test had ever run.
    """

    ANSWERS = "answers"
    """Assembled from the founder's own answers. Invents nothing, and every
    line names the question it came from."""

    MODEL = "model"
    """Enriched by a language model, over the same grounded material."""

    UNAVAILABLE = "unavailable"
    """No brain could be built, and `unavailable_reason` says why — the schema
    refuses this value without one."""


@dataclass(slots=True)
class Brain:
    """A built brain, before it is stored."""

    profile: str | None = None
    products_services: str | None = None
    target_customers: str | None = None
    brand_voice: str | None = None
    goals: str | None = None
    competitors: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    generated_by: str = GeneratedBy.ANSWERS.value
    unavailable_reason: str = ""
    documents_read: int = 0


def _plain(value: object) -> str:
    """`onboarding_answer.value` is jsonb, so a stored string arrives quoted.

    Rendering `"\\"Dates and dried fruit\\""` into the brain would put the JSON
    encoding in front of the founder, which reads as a bug and is one.
    """
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return value.strip()
        value = decoded
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


async def build(db: AsyncSession, *, workspace_id: UUID) -> Brain:
    """Assemble from the workspace's own answers. No model, no invention."""
    rows = (
        await db.execute(
            text(
                "SELECT question_key, value, department, is_assumption, answer_state"
                "  FROM onboarding_answer"
                " WHERE workspace_id = :w"
                " ORDER BY created_at"
            ),
            {"w": str(workspace_id)},
        )
    ).all()

    brain = Brain()
    company_name = (
        await db.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": str(workspace_id)})
    ).scalar_one_or_none()

    department_notes: list[str] = []

    for row in rows:
        # A Contributor's proposal is not a company fact until a manager says
        # so. The review gate exists for exactly this.
        if row.answer_state == "proposed":
            continue

        answer = _plain(row.value)
        if not answer:
            continue

        question = BY_KEY.get(row.question_key)
        prompt = question.prompt if question else row.question_key

        if row.is_assumption:
            # Into `assumptions`, never into the prose. An assumption that reads
            # as a fact is worse than no answer, because a document that later
            # contradicts it has nothing to correct.
            brain.assumptions.append(f"{prompt} — assumed: {answer}")
            brain.provenance.append(f"{row.question_key} (assumption)")
            continue

        brain.provenance.append(row.question_key)

        if row.department:
            department_notes.append(f"{row.department}: {prompt} {answer}")
            continue

        target = FIELD_FOR_KEY.get(row.question_key)
        if target == "goals" and brain.goals:
            brain.goals = f"{brain.goals}\n{answer}"
        elif target:
            setattr(brain, target, answer)

    if department_notes:
        brain.profile = "\n".join(department_notes)

    # The one line of prose that is assembled rather than quoted, and it only
    # ever joins facts already present above.
    headline = [company_name] if company_name else []
    if brain.products_services:
        headline.append(f"sells {brain.products_services}")
    if brain.target_customers:
        headline.append(f"to {brain.target_customers}")
    if headline:
        brain.profile = " ".join(headline) + (f"\n{brain.profile}" if brain.profile else "")

    if not brain.provenance:
        # Nothing answered yet. Unavailable **with a reason**, which the schema
        # insists on: "we could not build one" with no reason is
        # indistinguishable from a bug, and the founder decides whether to care.
        brain.generated_by = GeneratedBy.UNAVAILABLE.value
        brain.unavailable_reason = (
            "Nothing has been answered yet. The brain is built from your own "
            "answers, so it stays empty until onboarding has something in it."
        )

    return brain


async def store(db: AsyncSession, *, workspace_id: UUID, brain: Brain) -> int:
    """Supersede the current brain and insert the next version.

    Superseding **before** inserting, in one transaction, because
    `ux_company_brain_current` is a partial unique index on the un-superseded
    row — two current brains cannot exist, so the order is not a preference.
    """
    version = (
        await db.execute(
            text("SELECT COALESCE(MAX(version), 0) + 1 FROM company_brain WHERE workspace_id = :w"),
            {"w": str(workspace_id)},
        )
    ).scalar_one()

    await db.execute(
        text(
            "UPDATE company_brain SET superseded_at = now()"
            " WHERE workspace_id = :w AND superseded_at IS NULL"
        ),
        {"w": str(workspace_id)},
    )
    await db.execute(
        text(
            "INSERT INTO company_brain"
            " (workspace_id, version, profile, products_services, target_customers,"
            "  brand_voice, goals, competitors, assumptions, provenance, generated_by,"
            "  unavailable_reason, documents_read)"
            " VALUES (:w, :v, :profile, :products, :customers, :voice, :goals,"
            "         :competitors, :assumptions, :provenance, :by, :reason, :docs)"
        ),
        {
            "w": str(workspace_id),
            "v": version,
            "profile": brain.profile,
            "products": brain.products_services,
            "customers": brain.target_customers,
            "voice": brain.brand_voice,
            "goals": brain.goals,
            "competitors": brain.competitors,
            "assumptions": brain.assumptions,
            "provenance": brain.provenance,
            "by": brain.generated_by,
            "reason": brain.unavailable_reason,
            "docs": brain.documents_read,
        },
    )
    return int(version)


async def current(db: AsyncSession, *, workspace_id: UUID) -> Brain | None:
    row = (
        await db.execute(
            text(
                "SELECT profile, products_services, target_customers, brand_voice, goals,"
                "       competitors, assumptions, provenance, generated_by, unavailable_reason,"
                "       documents_read"
                "  FROM company_brain WHERE workspace_id = :w AND superseded_at IS NULL"
            ),
            {"w": str(workspace_id)},
        )
    ).first()
    if row is None:
        return None
    return Brain(
        profile=row.profile,
        products_services=row.products_services,
        target_customers=row.target_customers,
        brand_voice=row.brand_voice,
        goals=row.goals,
        competitors=list(row.competitors),
        assumptions=list(row.assumptions),
        provenance=list(row.provenance),
        generated_by=row.generated_by,
        unavailable_reason=row.unavailable_reason,
        documents_read=row.documents_read,
    )
