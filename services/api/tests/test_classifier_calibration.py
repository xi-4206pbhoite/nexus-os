"""The classifier proposes. It is measured, and it never overrides the gate.

`doc/12` P12: *calibration is measured, not asserted.* The 0.85 threshold has
been in this codebase since M5 and nothing has ever produced a confidence that
meant anything, so the number was a placeholder wearing a decision's clothes.
This reports precision and recall per department in the test output — the point
is the printed table as much as the assertion.

The rule that outranks all of it: **`classify_chunk` does not change.** If a
suggestion here would require editing the gate, the suggestion is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.documents.classify import ClassificationInput, classify_chunk
from app.documents.rules import CONFIDENT, propose
from app.domain.access import Sensitivity
from app.domain.scopes import Department, Scope


@dataclass(frozen=True)
class Labelled:
    text: str
    department: Department | None
    sensitive: bool = False


# Forty-two labelled samples: six per department, plus five sensitive ones and
# a deliberately ambiguous one. Small, and honest about being small — the point
# is that the number below is measured rather than claimed.
CORPUS: tuple[Labelled, ...] = (
    *[
        Labelled(t, Department.FINANCE)
        for t in (
            "Invoice 4410 is on the receivable ledger and remains unpaid.",
            "VAT reconciliation for the quarter against the ledger.",
            "The chart of accounts was updated with two payable codes.",
            "Ageing report: receivable balances over ninety days.",
            "Profit and loss against the balance sheet for the year.",
            "Payable run scheduled; ledger closed for reconciliation.",
        )
    ],
    *[
        Labelled(t, Department.SALES)
        for t in (
            "The quotation was sent and the deal moved down the pipeline.",
            "Price list applies a discount at the second pipeline stage.",
            "Lead qualification improved our close rate this quota period.",
            "Proposal template for the pipeline review.",
            "Quota attainment by deal size and discount band.",
            "Every lead in the pipeline needs a quotation this week.",
        )
    ],
    *[
        Labelled(t, Department.MARKETING)
        for t in (
            "Campaign impressions and click-through by audience segment.",
            "The brand guideline sets our tone of voice.",
            "SEO audit: audience reach and impressions.",
            "Campaign results, click-through against the audience plan.",
            "Tone of voice examples for the campaign.",
            "Audience segments for the SEO campaign.",
        )
    ],
    *[
        Labelled(t, Department.OPERATIONS)
        for t in (
            "The SOP covers supplier lead time and stock level checks.",
            "Purchase order raised against the delivery schedule.",
            "Standard operating procedure for supplier onboarding.",
            "Stock level review against supplier lead time.",
            "Delivery schedule updated after the purchase order.",
            "Supplier lead time exceeded the SOP threshold.",
        )
    ],
    *[
        Labelled(t, Department.HR)
        for t in (
            "The employee handbook covers annual leave and probation.",
            "Job description and appraisal cycle for the new role.",
            "Org chart updated; onboarding checklist attached.",
            "Probation review follows the appraisal in the handbook.",
            "Annual leave policy in the employee handbook.",
            "Job description approved; onboarding checklist issued.",
        )
    ],
    *[
        Labelled(t, Department.STRATEGY)
        for t in (
            "The business plan sets out a five-year market share goal.",
            "Board update for the investor on competitive landscape.",
            "Five-year business plan and market share targets.",
            "Investor board update: competitive landscape shift.",
            "Market share against the five-year business plan.",
            "Competitive landscape section of the board update.",
        )
    ],
    *[
        Labelled(t, Department.EXECUTIVE)
        for t in (
            "Commercial registration and trade licence renewal.",
            "Annual accounts filed; shareholder register updated.",
            "Capability statement and trade licence attached.",
            "Shareholder resolution on the commercial registration.",
            "Annual accounts and capability statement for the year.",
            "Trade licence copy with the commercial registration.",
        )
    ],
    # Sensitive. The department is incidental — what matters is that these are
    # withheld regardless of it.
    Labelled("Basic pay and salary bands for the payroll run.", Department.HR, sensitive=True),
    Labelled("Passport number and date of birth on file.", None, sensitive=True),
    Labelled("National ID recorded against the civil number.", None, sensitive=True),
    Labelled("Transfer to IBAN OM810180000001299123456 via SWIFT.", None, sensitive=True),
    Labelled("Account number and BIC for the supplier payment.", None, sensitive=True),
    # Genuinely ambiguous: one word from each of two departments.
    Labelled("The invoice was attached to the proposal.", None),
)


def test_precision_and_recall_are_reported_per_department(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The measurement, written to the test output.

    `noqa: T201` on the prints: this is the one place a `print` is the product
    rather than a leftover. `doc/12` P12 asks for precision and recall *reported
    in the test output*, because a threshold nobody can see the effect of is a
    threshold nobody can argue with — and a regression should be visible as a
    number moving, not only as a failing assertion.
    """
    labelled = [s for s in CORPUS if s.department is not None and not s.sensitive]

    print("\n  department   precision  recall   (n)")  # noqa: T201
    total_correct = 0
    for department in Department:
        expected = [s for s in labelled if s.department is department]
        if not expected:
            continue

        predicted = [
            s
            for s in labelled
            if propose(s.text).suggested_department is department
            and propose(s.text).confidence >= CONFIDENT
        ]
        true_positive = sum(1 for s in predicted if s.department is department)

        precision = true_positive / len(predicted) if predicted else 0.0
        recall = true_positive / len(expected)
        total_correct += true_positive
        print(  # noqa: T201
            f"  {department.value:12} {precision:8.2f}  {recall:6.2f}   ({len(expected)})"
        )

    overall = total_correct / len(labelled)
    print(f"  overall recall at confidence >= {CONFIDENT}: {overall:.2f}")  # noqa: T201

    # Deliberately modest. A high bar on forty-two hand-written samples would be
    # measuring how well the samples match the vocabulary I wrote, which is not
    # a fact about anything.
    assert overall >= 0.7, f"overall recall {overall:.0%} — the vocabulary has drifted"


def test_a_detected_pattern_outranks_the_vocabulary() -> None:
    """ "This contains an IBAN" is a fact about the characters. "This is a
    Finance document" is a judgement about the subject. Only the first is
    certain, and only the first should force withholding on its own."""
    salary_in_finance = propose("Payroll salary against the receivable ledger and invoice.")
    assert salary_in_finance.suggested_sensitivity is Sensitivity.PERSONAL
    assert salary_in_finance.suggested_scope is Scope.L5_PERSONAL
    assert salary_in_finance.confidence == 1.0


def test_an_ambiguous_chunk_goes_to_review_rather_than_guessing() -> None:
    """One Finance word and one Sales word is 0.5 — genuinely uncertain, below
    the threshold, and therefore withheld. A coin toss dressed as a decision is
    worse than an honest refusal."""
    proposal = propose("The invoice was attached to the proposal.")
    assert proposal.confidence < CONFIDENT
    assert proposal.suggested_scope is Scope.L5_PERSONAL

    decided = classify_chunk(proposal, uploader_id="u")
    assert decided.scope is Scope.L5_PERSONAL, "an uncertain chunk must not become visible"


def test_the_gate_still_withholds_everything_the_classifier_is_unsure_about() -> None:
    """`classify_chunk` is the guarantee and this phase does not touch it. If a
    suggestion required editing the gate, the suggestion would be wrong."""
    for sample in CORPUS:
        proposal = propose(sample.text)
        decided = classify_chunk(proposal, uploader_id="u")
        if proposal.confidence < CONFIDENT:
            assert decided.scope is Scope.L5_PERSONAL, sample.text


def test_a_classifier_failure_is_still_denied() -> None:
    """The pre-existing contract: no suggestion at all means withhold. The
    absence of a classifier was never a reason to default to visible."""
    failed = ClassificationInput(
        text="anything",
        suggested_scope=Scope.L1_COMPANY_PUBLIC,
        suggested_department=None,
        suggested_sensitivity=Sensitivity.NORMAL,
        confidence=0.0,
        classifier_failed=True,
    )
    assert classify_chunk(failed, uploader_id="u").scope is Scope.L5_PERSONAL
