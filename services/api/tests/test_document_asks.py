"""Three named asks per department (Q35), and the rules the wording follows.

The content is provisional — `doc/08` names only two of the twenty-one, and the
rest are drafted from what each department's questions and offerings consume.
These tests do not assert the wording. They assert the **properties** the
wording has to keep, so a future edit that breaks one fails here rather than
shipping: three per department, every one naming what it turns on, and none of
them promising a result.
"""

from __future__ import annotations

from app.domain.document_asks import ASKS, asks_for
from app.domain.scopes import Department


def test_every_department_has_exactly_three() -> None:
    """Q35 says three. Two feels thin and four is a chore, and the number is
    the spec's, not a preference."""
    assert set(ASKS) == set(Department)
    for department, asks in ASKS.items():
        assert len(asks) == 3, department


def test_every_ask_names_a_document_and_what_it_turns_on() -> None:
    """"Upload some documents" gets nothing. A founder uploads a file when they
    can picture which file and can see what it buys them."""
    for department, asks in ASKS.items():
        for ask in asks:
            assert ask.name.strip(), department
            assert ask.unlocks.strip(), department
            assert ask.unlocks.endswith("."), f"{department}: {ask.name}"


def test_no_ask_promises_a_finding() -> None:
    """I1, applied to the copy that asks for the file.

    `unlocks` says what NEXUS will be able to *do* — quote at your prices, age
    your receivables. It must never say what NEXUS will *find*, because that is
    a conclusion about a business whose documents we have not read yet, and the
    promise stays on the screen after the analysis disagrees with it.
    """
    forbidden = ("will show you that", "you will discover", "we expect", "typically", "most SMEs")
    for department, asks in ASKS.items():
        for ask in asks:
            lowered = ask.unlocks.lower()
            for phrase in forbidden:
                assert phrase not in lowered, f"{department}: {ask.name}"


def test_no_two_departments_ask_for_the_same_document() -> None:
    """A founder who selected four departments should not be asked for the same
    file four times. Duplication reads as the product not knowing what it has
    already got."""
    names = [ask.name for asks in ASKS.values() for ask in asks]
    assert len(names) == len(set(names))


def test_only_the_chosen_departments_are_asked() -> None:
    """Asking Finance's three of a company with no finance function is the same
    mistake as showing it a Finance dashboard."""
    chosen = frozenset({Department.SALES, Department.FINANCE})
    asked = asks_for(chosen)

    assert set(asked) == chosen
    assert Department.HR not in asked


def test_asking_nobody_is_an_empty_result_not_an_error() -> None:
    """A workspace that has not chosen departments yet reaches this before
    stage 4 has run. Nothing to ask for is a state, not a failure."""
    assert asks_for(frozenset()) == {}
