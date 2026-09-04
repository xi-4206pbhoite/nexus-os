"""All seven render states, each reachable and each with a distinct meaning.

`doc/12` P15. `WARMING` and `SELF_REPORTED` have existed in the enum since M5
and were unreachable in both layers — a state nothing can produce is a state
nobody has thought about, and it appears in code review as a handled case when
in fact it never happens.

The rule the whole ordering serves: **each state tells the founder something
different to do.** Two states that produce the same action should be one state,
and a state whose action is wrong is worse than no tile at all.
"""

from __future__ import annotations

import pytest

from app.domain.dashboards import (
    STALE_AFTER_DAYS,
    WARMUP_DAYS,
    Offering,
    Source,
    WidgetState,
    state_for,
)

BUILT = "3.4"
NEEDS_TWO = Offering(id=BUILT, name="X", shows="Y", needs=(Source.DOCUMENTS, Source.GA4))
BOTH = frozenset({Source.DOCUMENTS, Source.GA4})


def _delivered(monkeypatch: pytest.MonkeyPatch, offering: Offering) -> None:
    """Mark this offering built, so the states past `PLANNED` are reachable."""
    import app.domain.dashboards as dashboards

    monkeypatch.setattr(dashboards, "DELIVERED", frozenset({offering.id}))


def test_an_unbuilt_widget_is_planned_whatever_is_connected() -> None:
    """An unbuilt widget cannot be unlocked by connecting anything, and saying
    otherwise is a promise the product would then break."""
    assert state_for(NEEDS_TWO, connected=BOTH) is WidgetState.PLANNED


def test_nothing_connected_is_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    _delivered(monkeypatch, NEEDS_TWO)
    assert state_for(NEEDS_TWO, connected=frozenset()) is WidgetState.LOCKED


def test_some_connected_is_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    _delivered(monkeypatch, NEEDS_TWO)
    assert state_for(NEEDS_TWO, connected=frozenset({Source.GA4})) is WidgetState.PARTIAL


def test_everything_connected_is_live(monkeypatch: pytest.MonkeyPatch) -> None:
    _delivered(monkeypatch, NEEDS_TWO)
    assert state_for(NEEDS_TWO, connected=BOTH) is WidgetState.LIVE


def test_connected_but_thin_history_is_warming_never_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The distinction that matters most, and the reason `WARMING` exists.

    `PARTIAL` means *connect another source*. `WARMING` means *wait*. Telling
    somebody to connect something they already connected is how a product loses
    their trust in its own instructions.
    """
    _delivered(monkeypatch, NEEDS_TWO)
    # The assertion is only that it is `WARMING`. Adding `is not PARTIAL`
    # alongside it reads as a second check and is provably true from the first —
    # mypy says so, and a test that cannot fail is decoration.
    assert state_for(NEEDS_TWO, connected=BOTH, history_days=WARMUP_DAYS - 1) is (
        WidgetState.WARMING
    )


def test_enough_history_stops_warming(monkeypatch: pytest.MonkeyPatch) -> None:
    _delivered(monkeypatch, NEEDS_TWO)
    assert state_for(NEEDS_TWO, connected=BOTH, history_days=WARMUP_DAYS) is WidgetState.LIVE


def test_old_data_is_stale_not_live_and_not_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both halves.

    Not `LIVE`: a figure that was true last quarter reads as current unless the
    tile says otherwise, and somebody will decide on it. Not `UNAVAILABLE`
    either: the number is real and still worth seeing, with its age attached.
    """
    _delivered(monkeypatch, NEEDS_TWO)
    assert state_for(NEEDS_TWO, connected=BOTH, age_days=STALE_AFTER_DAYS + 1) is WidgetState.STALE
    assert state_for(NEEDS_TWO, connected=BOTH, age_days=STALE_AFTER_DAYS) is WidgetState.LIVE


def test_a_number_the_founder_typed_is_labelled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A number they typed and a number we measured must never look identical.
    The second can contradict them; the first cannot."""
    _delivered(monkeypatch, NEEDS_TWO)
    assert state_for(NEEDS_TWO, connected=BOTH, self_reported=True) is WidgetState.SELF_REPORTED


def test_a_failed_generation_outranks_everything_below_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The inputs being present says nothing about whether the answer was
    computable. Rendering `LIVE` over a failed generation shows a tile with no
    number in it."""
    _delivered(monkeypatch, NEEDS_TWO)
    assert (
        state_for(NEEDS_TWO, connected=BOTH, unavailable_reason="budget_exhausted")
        is WidgetState.UNAVAILABLE
    )


def test_every_state_is_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A state nothing can produce is a state nobody has thought about — it
    reads as a handled case in review and never happens in fact. `WARMING` and
    `SELF_REPORTED` were exactly that until this phase."""
    _delivered(monkeypatch, NEEDS_TWO)

    produced = {
        state_for(NEEDS_TWO, connected=BOTH),
        state_for(NEEDS_TWO, connected=frozenset()),
        state_for(NEEDS_TWO, connected=frozenset({Source.GA4})),
        state_for(NEEDS_TWO, connected=BOTH, history_days=0),
        state_for(NEEDS_TWO, connected=BOTH, age_days=STALE_AFTER_DAYS + 1),
        state_for(NEEDS_TWO, connected=BOTH, self_reported=True),
        state_for(NEEDS_TWO, connected=BOTH, unavailable_reason="x"),
        state_for(Offering(id="unbuilt", name="X", shows="Y", needs=()), connected=BOTH),
    }
    assert produced == set(WidgetState), f"unreachable: {set(WidgetState) - produced}"


def test_the_defaults_preserve_the_old_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every existing caller passes only `connected`. With nothing else given,
    the four new branches are unreachable — which is exactly how this behaved
    before the phase, and why no caller had to change."""
    _delivered(monkeypatch, NEEDS_TWO)
    for connected in (frozenset(), frozenset({Source.GA4}), BOTH):
        assert state_for(NEEDS_TWO, connected=connected) in (
            WidgetState.LOCKED,
            WidgetState.PARTIAL,
            WidgetState.LIVE,
        )
