"""Scope classification, with default deny (I4).

Doc 06 §3.3: *"Scope classification decides who can see a chunk, and it is done
by a classifier that will sometimes be wrong. One misclassified payroll export
is a silent, permanent, workspace-wide breach."*

`classify_chunk` is the **gate**, not the classifier. Something upstream
proposes a scope and a confidence; this decides whether to believe it. That
split matters: it means improving the classifier can never weaken the guarantee,
because the guarantee lives here and is tested against every failure mode
independently of how the suggestion was produced.

Every failure resolves the same way — L5, uploader-only, review queue. Not L2
"because it looked internal", and not L1 "because parsing failed so there is
nothing sensitive in an empty string".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.access import Sensitivity
from app.domain.scopes import Department, Scope

# Below this, the suggestion is not acted on. Deliberately high: the cost of an
# unnecessary review is a queue item, and the cost of a wrong auto-approval is
# a permanent workspace-wide disclosure. Those are not symmetric.
CONFIDENCE_THRESHOLD = 0.85


class ReviewState(StrEnum):
    """The value written to `chunk.review_state`, in the column's own vocabulary.

    These four strings were once a different four — `needs_review`,
    `human_approved`, `quarantined` — while `ck_chunk_review_state` permitted
    `pending_review`, `approved`, `rejected`. Two independent lists, and nothing
    could see they had drifted: the enum type-checked, the constraint was valid
    SQL, and the only place they met was an INSERT no test had ever run. Every
    chunk of every upload violated the constraint, and the partial index
    `ix_chunk_pending_review` and both review-queue queries filtered on a value
    nothing could write, so the queue was permanently empty.

    The SQL vocabulary won because three things already depended on it. The
    enum is now the single source of truth in the other direction, and
    `tests/test_constraint_enum_parity.py` asserts the two are set-equal.
    """

    AUTO_APPROVED = "auto_approved"
    """Classified with enough confidence to be reachable without a human."""

    PENDING_REVIEW = "pending_review"
    """Withheld, awaiting a person. Every default-deny path lands here."""

    APPROVED = "approved"
    """A person confirmed it, and it holds the scope they granted."""

    REJECTED = "rejected"
    """A person declined it. It stays unreachable."""


def review_state_code(state: ReviewState) -> str:
    """The value to write to `chunk.review_state`.

    An identity today, and deliberately still a function. It is the named write
    path — the counterpart of `scope_code`, whose translation is not an identity
    — so that every INSERT and UPDATE goes through one place. The reason the
    drift above was invisible is that there was no such place: each call site
    reached for `.value` or a bare literal of its own, so nothing tied the SQL
    vocabulary to the enum except the hope that both would be edited together.
    """
    return state.value


# Scopes an automatic classifier may assign.
#
# L1 is excluded because it is company-*public* — material that leaves the
# company — and nothing automatic should put content there. L4 is excluded
# because it is reachable only by being named on the item (doc 06 §2.3), so an
# automatically-assigned L4 chunk would be unreachable by everyone including
# the Owner. L5 is not "assignable"; it is where things land when we decline to
# decide.
ASSIGNABLE_SCOPES = frozenset({Scope.L2_COMPANY_INTERNAL, Scope.L3_DEPARTMENT})

# Confidence is irrelevant for these: a payroll export the classifier is 99%
# sure about is precisely the document that must not auto-publish.
REQUIRES_HUMAN = frozenset({Sensitivity.PERSONAL, Sensitivity.RESTRICTED})


@dataclass(frozen=True, slots=True)
class ClassificationInput:
    text: str
    suggested_scope: Scope
    suggested_department: Department | None
    suggested_sensitivity: Sensitivity
    confidence: float
    parse_failed: bool = False
    classifier_failed: bool = False


@dataclass(frozen=True, slots=True)
class Classification:
    scope: Scope
    department: Department | None
    sensitivity: Sensitivity
    review_state: ReviewState
    classified_by: str
    confidence: float
    owner_user_id: str | None
    """Set when the chunk is L5 — the uploader, and nobody else."""
    reason: str
    """Why this outcome. Shown in the review queue, so a human can judge the
    decision rather than only its result."""


def _withhold(
    source: ClassificationInput, *, uploader_id: str, classified_by: str, reason: str
) -> Classification:
    """The single default-deny outcome. Every failure path routes through here."""
    return Classification(
        scope=Scope.L5_PERSONAL,
        department=None,
        sensitivity=source.suggested_sensitivity,
        review_state=ReviewState.PENDING_REVIEW,
        classified_by=classified_by,
        confidence=source.confidence,
        owner_user_id=uploader_id,
        reason=reason,
    )


def classify_chunk(
    source: ClassificationInput, *, uploader_id: str, classifier_name: str = "rules-v1"
) -> Classification:
    """Decide a chunk's scope, withholding whenever there is any doubt."""
    if source.parse_failed:
        return _withhold(
            source,
            uploader_id=uploader_id,
            classified_by=f"{classifier_name}:parse-failed",
            reason="The document could not be read, so its contents are unknown.",
        )

    if source.classifier_failed:
        return _withhold(
            source,
            uploader_id=uploader_id,
            classified_by=f"{classifier_name}:classifier-failed",
            reason="Classification failed, so no scope could be established.",
        )

    if source.confidence < CONFIDENCE_THRESHOLD:
        return _withhold(
            source,
            uploader_id=uploader_id,
            classified_by=classifier_name,
            reason=(
                f"Confidence {source.confidence:.2f} is below the "
                f"{CONFIDENCE_THRESHOLD:.2f} threshold."
            ),
        )

    if source.suggested_sensitivity in REQUIRES_HUMAN:
        # Doc 06 §3.3 — personal and restricted material needs human
        # confirmation before it becomes reachable by anyone else.
        return Classification(
            scope=Scope.L5_PERSONAL,
            department=source.suggested_department,
            sensitivity=source.suggested_sensitivity,
            review_state=ReviewState.PENDING_REVIEW,
            classified_by=classifier_name,
            confidence=source.confidence,
            owner_user_id=uploader_id,
            reason=(
                f"Looks {source.suggested_sensitivity.value}; sensitive material "
                "is confirmed by a person before anyone else can reach it."
            ),
        )

    if source.suggested_scope not in ASSIGNABLE_SCOPES:
        return _withhold(
            source,
            uploader_id=uploader_id,
            classified_by=classifier_name,
            reason=(
                f"{source.suggested_scope.name} is not assignable automatically; a person decides."
            ),
        )

    if source.suggested_scope is Scope.L3_DEPARTMENT and source.suggested_department is None:
        # A high-confidence answer that cannot say *which* department is a
        # low-information answer wearing a high-confidence number. An L3 chunk
        # with no department is reachable by anyone holding any L3 access.
        return _withhold(
            source,
            uploader_id=uploader_id,
            classified_by=classifier_name,
            reason="Department-level, but the department could not be identified.",
        )

    return Classification(
        scope=source.suggested_scope,
        department=source.suggested_department,
        sensitivity=source.suggested_sensitivity,
        review_state=ReviewState.AUTO_APPROVED,
        classified_by=classifier_name,
        confidence=source.confidence,
        owner_user_id=None,
        reason="Classified with sufficient confidence.",
    )
