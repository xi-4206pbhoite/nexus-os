"""Three named documents to ask each department for (Q35).

**Named beats generic.** "Upload some documents" gets nothing; "your current
price list, a proposal you are proud of, and your services one-pager" gets
three files, because a founder can picture each one and knows where it lives.
`doc/11` stage 5 makes this a rule, and `doc/09` §6.2 makes stage 5 skippable —
so these asks have to earn the upload rather than demand it, which is why every
one of them says what it turns on.

**Provisional content, pending review.** `doc/08` names only two of these
directly — Finance's *"Upload this year's budget"* and Sales' *"Add your price
list"* — and the dashboard offerings supply one document-needing tile per
department and none at all for People or Strategy. The remaining asks are
drafted from what each department's questions and offerings actually consume,
which keeps them traceable to something, but the wording and the choice of
document are a business judgement Parul has not made yet. Correct them freely;
the mechanism does not depend on the text.

**No numbers are asserted here.** Every `unlocks` says what the document lets
NEXUS *do*, never what it will find — a promise about a result we have not
computed would be the product inventing a conclusion before it has read a file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.domain.scopes import Department


@dataclass(frozen=True, slots=True)
class DocumentAsk:
    """One named document, and what having it turns on."""

    name: str
    """What to go and find, in the founder's words, not ours."""

    unlocks: str
    """What NEXUS can do once it has this. A capability, never a finding."""


ASKS: Final[dict[Department, tuple[DocumentAsk, ...]]] = {
    Department.SALES: (
        DocumentAsk(
            name="Your current price list",
            unlocks="Quoting at your real prices instead of asking you every time.",
        ),
        DocumentAsk(
            name="A proposal you were proud of",
            unlocks="Drafting new proposals in your structure and your language.",
        ),
        DocumentAsk(
            name="Your services or product one-pager",
            unlocks="Answering what you sell without you re-explaining it.",
        ),
    ),
    Department.FINANCE: (
        DocumentAsk(
            name="This year's budget",
            unlocks="Comparing what happened against what you planned.",
        ),
        DocumentAsk(
            name="Your last three months of invoices, or an export of them",
            unlocks="Ageing your receivables and seeing who pays late.",
        ),
        DocumentAsk(
            name="Your chart of accounts",
            unlocks="Reading your own account names back to you instead of generic ones.",
        ),
    ),
    Department.MARKETING: (
        DocumentAsk(
            name="Your brand or tone-of-voice guide",
            unlocks="Writing in your voice rather than a generic one.",
        ),
        DocumentAsk(
            name="A campaign report you have kept",
            unlocks="Reading past results in the format you already report them.",
        ),
        DocumentAsk(
            name="Your website copy, or a deck about what you do",
            unlocks="Describing your positioning without inventing it.",
        ),
    ),
    Department.OPERATIONS: (
        DocumentAsk(
            name="A standard operating procedure you actually follow",
            unlocks="Answering how things are done here, from your own document.",
        ),
        DocumentAsk(
            name="A supplier contract or purchase agreement",
            unlocks="Knowing your real lead times and terms rather than assuming them.",
        ),
        DocumentAsk(
            name="A recent project plan or delivery schedule",
            unlocks="Reading how you scope and sequence work.",
        ),
    ),
    Department.HR: (
        DocumentAsk(
            name="Your employee handbook or HR policy",
            unlocks="Answering leave and policy questions from your own rules.",
        ),
        DocumentAsk(
            name="A job description you have used",
            unlocks="Writing new ones that match how you already hire.",
        ),
        DocumentAsk(
            name="Your org chart, or a list of who reports to whom",
            unlocks="Routing approvals and questions to the right person.",
        ),
    ),
    Department.STRATEGY: (
        DocumentAsk(
            name="Your business plan, or the deck you raised on",
            unlocks="Holding you to the plan you actually wrote.",
        ),
        DocumentAsk(
            name="Board or investor updates you have sent",
            unlocks="Continuing the story you have already been telling.",
        ),
        DocumentAsk(
            name="Any competitor or market research you have gathered",
            unlocks="Starting from what you already know rather than from nothing.",
        ),
    ),
    Department.EXECUTIVE: (
        DocumentAsk(
            name="Your company profile or capability statement",
            unlocks="One accurate description of the company for everything else to build on.",
        ),
        DocumentAsk(
            name="Your commercial registration or trade licence",
            unlocks="Confirming the legal entity, so filings and dates are yours and not a guess.",
        ),
        DocumentAsk(
            name="Last year's annual accounts, if you have them",
            unlocks="A baseline to measure this year against.",
        ),
    ),
}


def asks_for(departments: frozenset[Department]) -> dict[Department, tuple[DocumentAsk, ...]]:
    """The asks for the departments this company runs, and no others.

    Asking Finance's three of a company with no finance function is the same
    mistake as showing it a Finance dashboard: it makes the product's shape more
    important than the customer's, which is why department selection exists.
    """
    return {d: ASKS[d] for d in ASKS if d in departments}
