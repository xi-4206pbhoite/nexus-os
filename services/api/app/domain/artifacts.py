"""An artifact inherits `max(inputs)`, and declassifying is a logged decision (I6).

`doc/12` P21. An artifact is built from facts, chunks and generated prose, and
the question it answers is: **who may see the thing made out of these?**

The answer is the strictest of its inputs, always. A summary of one L4 figure and
twenty L2 ones is L4 — the restricted number is *in* it, and averaging the scopes
or taking the common case would produce a document that reads as shareable and
contains something that is not.

**Staleness is marked, never corrected.** When a grounding fact changes the
artifact does not silently regenerate: somebody may have sent it to a client,
and the version they hold has to go on existing. It is flagged so the next
reader knows the ground moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

from app.domain.scopes import Scope

SHAREABLE_WITHOUT_CONFIRMATION: Final = Scope.L2_COMPANY_INTERNAL
"""L2 is company-internal — the highest scope at which "this leaves the
building" is not by itself a disclosure decision."""


@dataclass(frozen=True, slots=True)
class Artifact:
    """A generated document, its inputs, and the scope it inherited."""

    id: UUID
    version: int
    input_scopes: tuple[Scope, ...]
    input_fact_keys: tuple[str, ...] = field(default=())
    declassified_to: Scope | None = None
    declassified_by_user_id: UUID | None = None
    declassified_reason: str = ""
    stale: bool = False

    @property
    def inherited_scope(self) -> Scope:
        """`max(inputs)` (I6). The strictest input decides.

        **An empty input list is L5, not L1.** An artifact built from nothing
        has no provenance, and the safe reading of "we cannot tell where this
        came from" is the most restrictive one — the opposite default would let
        a bug in input tracking silently publish something.
        """
        return max(self.input_scopes, default=Scope.L5_PERSONAL)

    @property
    def effective_scope(self) -> Scope:
        return self.declassified_to or self.inherited_scope

    @property
    def needs_confirmation_to_share(self) -> bool:
        return self.effective_scope > SHAREABLE_WITHOUT_CONFIRMATION


def declassify(artifact: Artifact, *, to: Scope, by_user_id: UUID, reason: str) -> Artifact:
    """Lower an artifact's scope. **Explicit, logged, never silent.**

    Requires a reason, because this is the one operation that makes something
    visible to people its inputs excluded — and "who decided this could be
    shared, and why" is the first question asked afterwards.

    Refuses to *raise* scope: that is not declassification, and an artifact
    quietly becoming more restricted breaks links for people who already hold it.
    """
    if not reason.strip():
        raise ValueError(
            "Declassifying needs a reason. It is the operation that makes something "
            "visible to people its inputs excluded, and the record is the point."
        )

    if to >= artifact.inherited_scope:
        raise ValueError(
            f"{to.name} is not lower than the inherited {artifact.inherited_scope.name}. "
            "Declassification only ever loosens; tightening breaks links people hold."
        )

    return Artifact(
        id=artifact.id,
        version=artifact.version,
        input_scopes=artifact.input_scopes,
        input_fact_keys=artifact.input_fact_keys,
        declassified_to=to,
        declassified_by_user_id=by_user_id,
        declassified_reason=reason,
        stale=artifact.stale,
    )


def mark_stale(artifact: Artifact, *, changed_fact: str) -> Artifact:
    """Flag an artifact whose grounding moved. **Marked, never regenerated.**

    Somebody may have sent this to a client, and the version they hold has to go
    on existing. Regenerating in place changes a document after it was quoted,
    which is worse than an out-of-date one that admits it.
    """
    if changed_fact not in artifact.input_fact_keys:
        return artifact
    return Artifact(
        id=artifact.id,
        version=artifact.version,
        input_scopes=artifact.input_scopes,
        input_fact_keys=artifact.input_fact_keys,
        declassified_to=artifact.declassified_to,
        declassified_by_user_id=artifact.declassified_by_user_id,
        declassified_reason=artifact.declassified_reason,
        stale=True,
    )
