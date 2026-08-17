"""I4 — default deny on classification.

Doc 07 M5's acceptance: *"a low-confidence document lands in L5 and the review
queue, and nothing is silently visible."* Doc 06 §3.3 states the stake plainly:

> *Scope classification decides who can see a chunk, and it is done by a
> classifier that will sometimes be wrong. **One misclassified payroll export is
> a silent, permanent, workspace-wide breach.***

So every failure mode resolves the same way — to L5, visible only to the
uploader, in a review queue. Not to L2 "because it looked internal", not to L1
"because parsing failed and there is nothing sensitive in an empty string".

These are written before the classifier, because the classifier's job is to be
*better* than default-deny, never to be trusted instead of it.
"""

from __future__ import annotations

import pytest

from app.documents.classify import (
    CONFIDENCE_THRESHOLD,
    ClassificationInput,
    ReviewState,
    classify_chunk,
)
from app.domain.access import Sensitivity
from app.domain.scopes import Department, Scope

UPLOADER = "11111111-1111-1111-1111-111111111111"


def make(
    text: str = "Ordinary paragraph about our services.",
    *,
    confidence: float = 0.95,
    suggested_scope: Scope = Scope.L2_COMPANY_INTERNAL,
    suggested_department: Department | None = None,
    suggested_sensitivity: Sensitivity = Sensitivity.NORMAL,
    parse_failed: bool = False,
    classifier_failed: bool = False,
) -> ClassificationInput:
    return ClassificationInput(
        text=text,
        suggested_scope=suggested_scope,
        suggested_department=suggested_department,
        suggested_sensitivity=suggested_sensitivity,
        confidence=confidence,
        parse_failed=parse_failed,
        classifier_failed=classifier_failed,
    )


# ── The three failure modes all land in the same place ────────


def test_low_confidence_lands_in_l5_and_the_review_queue() -> None:
    result = classify_chunk(make(confidence=CONFIDENCE_THRESHOLD - 0.01), uploader_id=UPLOADER)

    assert result.scope is Scope.L5_PERSONAL
    assert result.owner_user_id == UPLOADER
    assert result.review_state is ReviewState.NEEDS_REVIEW


def test_a_parse_failure_lands_in_l5_not_in_the_open() -> None:
    """Failing to read a document is not evidence that it is harmless."""
    result = classify_chunk(make(text="", parse_failed=True, confidence=0.99), uploader_id=UPLOADER)

    assert result.scope is Scope.L5_PERSONAL
    assert result.review_state is ReviewState.NEEDS_REVIEW


def test_a_classifier_failure_lands_in_l5() -> None:
    """A crashed classifier must not mean 'no objection raised'."""
    result = classify_chunk(make(classifier_failed=True, confidence=0.99), uploader_id=UPLOADER)

    assert result.scope is Scope.L5_PERSONAL
    assert result.review_state is ReviewState.NEEDS_REVIEW


@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.49, CONFIDENCE_THRESHOLD - 0.001])
def test_everything_below_the_threshold_defaults_deny(confidence: float) -> None:
    result = classify_chunk(make(confidence=confidence), uploader_id=UPLOADER)
    assert result.scope is Scope.L5_PERSONAL


def test_the_threshold_boundary_is_inclusive_upward() -> None:
    """At exactly the threshold the classifier is trusted; below it, never."""
    at = classify_chunk(make(confidence=CONFIDENCE_THRESHOLD), uploader_id=UPLOADER)
    below = classify_chunk(make(confidence=CONFIDENCE_THRESHOLD - 0.001), uploader_id=UPLOADER)

    assert at.scope is not Scope.L5_PERSONAL
    assert below.scope is Scope.L5_PERSONAL


# ── Confident classification is honoured ──────────────────────


def test_a_confident_classification_is_used() -> None:
    """Default-deny must not make the classifier pointless."""
    result = classify_chunk(
        make(suggested_scope=Scope.L2_COMPANY_INTERNAL, confidence=0.98), uploader_id=UPLOADER
    )
    assert result.scope is Scope.L2_COMPANY_INTERNAL
    assert result.review_state is ReviewState.AUTO_APPROVED


def test_a_confident_l3_classification_keeps_its_department() -> None:
    result = classify_chunk(
        make(
            suggested_scope=Scope.L3_DEPARTMENT,
            suggested_department=Department.FINANCE,
            confidence=0.97,
        ),
        uploader_id=UPLOADER,
    )
    assert result.scope is Scope.L3_DEPARTMENT
    assert result.department is Department.FINANCE


def test_an_l3_classification_without_a_department_is_not_trusted() -> None:
    """An L3 chunk with no department is reachable by anyone with any L3.

    The classifier said L3 but could not say *which* department — that is a
    low-information answer wearing a high-confidence number.
    """
    result = classify_chunk(
        make(suggested_scope=Scope.L3_DEPARTMENT, suggested_department=None, confidence=0.99),
        uploader_id=UPLOADER,
    )
    assert result.scope is Scope.L5_PERSONAL
    assert result.review_state is ReviewState.NEEDS_REVIEW


# ── Sensitive material needs a human, however confident ───────


@pytest.mark.parametrize("sensitivity", [Sensitivity.PERSONAL, Sensitivity.RESTRICTED])
def test_sensitive_material_requires_human_confirmation(sensitivity: Sensitivity) -> None:
    """Doc 06 §3.3 — *"Anything classified sensitivity: personal | restricted
    requires human confirmation before it becomes reachable by anyone else."*

    Confidence is irrelevant here. A payroll export the classifier is 99% sure
    about is exactly the document that must not auto-publish.
    """
    result = classify_chunk(
        make(suggested_sensitivity=sensitivity, confidence=0.99), uploader_id=UPLOADER
    )

    assert result.scope is Scope.L5_PERSONAL
    assert result.review_state is ReviewState.NEEDS_REVIEW
    assert result.sensitivity is sensitivity


def test_financial_sensitivity_alone_does_not_force_review() -> None:
    """A price list is financial and routine. Forcing review on every invoice
    would make the queue meaningless, and a queue nobody reads is worse than
    no queue."""
    result = classify_chunk(
        make(
            suggested_sensitivity=Sensitivity.FINANCIAL,
            suggested_scope=Scope.L3_DEPARTMENT,
            suggested_department=Department.FINANCE,
            confidence=0.97,
        ),
        uploader_id=UPLOADER,
    )
    assert result.scope is Scope.L3_DEPARTMENT
    assert result.review_state is ReviewState.AUTO_APPROVED


# ── Nothing is silently visible ───────────────────────────────


def test_every_outcome_records_who_decided_and_how_sure() -> None:
    """Doc 06 §4.1 — the chunk stores `classified_by`, `confidence` and
    `review_state`. Without them a wrong classification cannot be found later."""
    for case in (make(), make(confidence=0.1), make(parse_failed=True)):
        result = classify_chunk(case, uploader_id=UPLOADER)
        assert result.classified_by
        assert 0.0 <= result.confidence <= 1.0
        assert result.review_state in set(ReviewState)


def test_no_input_ever_yields_l1_by_default() -> None:
    """L1 is company-public — material that leaves the company.

    Nothing an automatic classifier decides should land there without a human,
    so it is asserted across the whole range rather than case by case.
    """
    for confidence in (0.0, 0.5, 0.9, 1.0):
        for scope in Scope:
            result = classify_chunk(
                make(suggested_scope=scope, confidence=confidence), uploader_id=UPLOADER
            )
            assert result.scope is not Scope.L1_COMPANY_PUBLIC, (
                f"classifier promoted a chunk to L1 (suggested={scope}, conf={confidence})"
            )


def test_l4_is_never_assigned_automatically() -> None:
    """L4 is reachable only by being named on the item (doc 06 §2.3).

    A classifier assigning L4 would create content nobody can reach — including
    the Owner — which is a different failure but still a failure.
    """
    result = classify_chunk(
        make(suggested_scope=Scope.L4_RESTRICTED, confidence=0.99), uploader_id=UPLOADER
    )
    assert result.scope is not Scope.L4_RESTRICTED
    assert result.review_state is ReviewState.NEEDS_REVIEW
