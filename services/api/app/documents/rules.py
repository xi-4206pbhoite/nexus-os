"""A rules classifier: it **proposes**, it never decides.

`classify_chunk` is the gate, it is already proved, and this does not touch it.
`doc/12` P12 is explicit: *if the gate needs editing, the classifier is wrong.*
Everything here produces a `ClassificationInput` — a suggestion with a
confidence — and the gate does what it has always done with it.

**Why rules before a model.** A rules classifier is wrong in ways you can read.
When it puts a payroll export in Finance you can point at the word that did it.
A model that is wrong fifteen percent of the time gives you a number and no
sentence — and the gate's 0.85 threshold was chosen before anything in this
codebase produced a confidence that meant anything at all.

**Sensitivity is detected, not inferred.** Salary figures, IBANs, passport and
national ID numbers are *patterns*: one either matched or it did not. That is a
far stronger claim than "this reads like an HR document", and it is the claim
that should drive withholding — so a matched pattern sets sensitivity at full
confidence regardless of what the department vocabulary suggested.
"""

from __future__ import annotations

import re
from typing import Final

from app.documents.classify import ClassificationInput
from app.domain.access import Sensitivity
from app.domain.scopes import Department, Scope

# Vocabulary per department. Deliberately narrow: a word belongs here only if it
# rarely appears outside its department, because a false positive sends a
# document to the wrong dashboard while a false negative merely leaves it
# unclassified — and unclassified is a state the review queue already handles.
VOCABULARY: Final[dict[Department, tuple[str, ...]]] = {
    Department.FINANCE: (
        "invoice",
        "receivable",
        "payable",
        "ledger",
        "vat",
        "reconciliation",
        "chart of accounts",
        "profit and loss",
        "balance sheet",
        "ageing",
    ),
    Department.SALES: (
        "quotation",
        "proposal",
        "pipeline",
        "lead",
        "deal",
        "quota",
        "price list",
        "discount",
        "close rate",
    ),
    Department.MARKETING: (
        "campaign",
        "impressions",
        "click-through",
        "brand guideline",
        "tone of voice",
        "seo",
        "audience",
    ),
    Department.OPERATIONS: (
        "sop",
        "standard operating procedure",
        "lead time",
        "supplier",
        "purchase order",
        "delivery schedule",
        "stock level",
    ),
    Department.HR: (
        "employee handbook",
        "job description",
        "annual leave",
        "probation",
        "appraisal",
        "org chart",
        "onboarding checklist",
    ),
    Department.STRATEGY: (
        "business plan",
        "board update",
        "investor",
        "market share",
        "competitive landscape",
        "five-year",
    ),
    Department.EXECUTIVE: (
        "commercial registration",
        "trade licence",
        "annual accounts",
        "capability statement",
        "shareholder",
    ),
}

# Patterns that make a chunk sensitive regardless of its subject. Each is
# something a person would be harmed by seeing next to their name.
PERSONAL_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("passport", re.compile(r"\bpassport\s*(no|number|#)\b", re.I)),
    ("national id", re.compile(r"\b(national\s*id|civil\s*number)\b", re.I)),
    ("salary", re.compile(r"\b(salary|payroll|gross\s+pay|basic\s+pay)\b", re.I)),
    ("date of birth", re.compile(r"\b(date\s+of\s+birth|d\.?o\.?b\.?)\b", re.I)),
)

FINANCIAL_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    # IBAN: two letters, two check digits, then up to thirty alphanumerics.
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("bank account", re.compile(r"\b(account\s*(no|number)|swift|bic)\b", re.I)),
)

CONFIDENT: Final = 0.85
"""The gate's threshold, unchanged and not ours to move. What this phase adds is
a confidence that *means* something, not a new number."""


def _department_for(text: str) -> tuple[Department | None, float]:
    """The department whose vocabulary the text hits hardest, and how sure.

    Confidence is the winner's share of all hits, so a document matching one
    Finance word and one HR word scores 0.5 — genuinely uncertain, below the
    threshold, and therefore sent to review. That is the correct outcome rather
    than a coin toss dressed as a decision.
    """
    lowered = text.lower()
    hits = {
        department: sum(lowered.count(word) for word in words)
        for department, words in VOCABULARY.items()
    }
    total = sum(hits.values())
    if not total:
        return None, 0.0

    winner = max(hits, key=lambda d: hits[d])
    return winner, hits[winner] / total


def _matched(patterns: tuple[tuple[str, re.Pattern[str]], ...], text: str) -> list[str]:
    return [name for name, pattern in patterns if pattern.search(text)]


def propose(text: str) -> ClassificationInput:
    """Suggest a scope, department and sensitivity for one chunk.

    **A matched pattern overrides the vocabulary and carries full confidence.**
    "This contains an IBAN" is a fact about the characters; "this is a Finance
    document" is a judgement about the subject. Only the first is certain, and
    only the first should force withholding on its own.
    """
    personal = _matched(PERSONAL_PATTERNS, text)
    financial = _matched(FINANCIAL_PATTERNS, text)
    department, confidence = _department_for(text)

    if personal:
        # L5, uploader-only. A salary line is not "Finance data with a caveat";
        # it is somebody's pay, and which department it sits in has no bearing
        # on who may read it.
        return ClassificationInput(
            text=text,
            suggested_scope=Scope.L5_PERSONAL,
            suggested_department=department,
            suggested_sensitivity=Sensitivity.PERSONAL,
            confidence=1.0,
        )

    if financial:
        return ClassificationInput(
            text=text,
            suggested_scope=Scope.L4_RESTRICTED,
            suggested_department=department or Department.FINANCE,
            suggested_sensitivity=Sensitivity.FINANCIAL,
            confidence=1.0,
        )

    if department is not None and confidence >= CONFIDENT:
        return ClassificationInput(
            text=text,
            suggested_scope=Scope.L3_DEPARTMENT,
            suggested_department=department,
            suggested_sensitivity=Sensitivity.NORMAL,
            confidence=confidence,
        )

    # Nothing recognised, or recognised weakly. **Not a guess.** The suggestion
    # is the most restrictive scope with a confidence the gate will refuse, so
    # the chunk goes to review — which is where an uncertain document belongs.
    return ClassificationInput(
        text=text,
        suggested_scope=Scope.L5_PERSONAL,
        suggested_department=department,
        suggested_sensitivity=Sensitivity.NORMAL,
        confidence=confidence,
    )
