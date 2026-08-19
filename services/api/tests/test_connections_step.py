"""The connection step, which connects nothing and says so.

Doc 04 §5's stage 4 with M10 unbuilt and both its prerequisites open (**D3** Google
credentials, **D10** which CRM). The temptation in that situation is a step that
looks finished — a row of provider logos with "Connect" buttons that do nothing, or
worse, a state that reads as connected. Either would be the fabricated-capability
failure the product's whole position rests on avoiding.

So what is asserted here is mostly about restraint:

- **Nothing is ever connected.** `connected` is false for every tool and the count is
  zero, both stated in the payload rather than left for a client to assume.
- **Only the customer's own tools are offered.** `Source` has sixteen members;
  five are things a customer has. Offering `HISTORY` or `PAGESPEED` would be asking
  someone to connect time, or to solve our procurement.
- **The unlock counts are derived, not written.** They come from the same offering
  definitions the director pages render, so a count on this screen and a locked tile
  on that one cannot disagree.

That last one earned its test the hard way: `Source.SEARCH_CONSOLE` unlocked
*nothing* until offering 3.7's `needs` was corrected, so this step would have offered
a tool that changes no tile — while doc 05 §3.7 says in as many words that rankings
need it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.deps import current_scope
from app.domain.dashboards import (
    CONNECTABLE,
    DIRECTORS,
    LABELS,
    Source,
    offerings_needing,
    state_for,
)
from app.domain.onboarding import BY_KEY, CONNECTABLE_TOOLS, TOOL_LABELS, Pass
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.main import create_app

NOT_A_CUSTOMER_TOOL = (
    Source.CRAWL,
    Source.ONBOARDING,
    Source.ROSTER,
    Source.OPS_LAYER,
    Source.HISTORY,
    Source.LANGUAGE_MODEL,
    Source.PAGESPEED,
    Source.DATAFORSEO,
    Source.ENRICHMENT,
    Source.TENDER_FEED,
)


@pytest.fixture
def client():  # type: ignore[no-untyped-def]
    app = create_app()

    def scope() -> ScopedSession:
        return ScopedSession(
            user_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            role=Role.OWNER,
            departments=frozenset({Department.EXECUTIVE}),
        )

    app.dependency_overrides[current_scope] = scope
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Nothing is connected, and the payload says so ─────────────


def test_no_tool_is_ever_reported_as_connected(client) -> None:  # type: ignore[no-untyped-def]
    """There is no connector. A single `connected: true` here would be a lie the
    dashboards would then contradict by rendering the same source as Locked."""
    body = client.get("/onboarding/connections").json()

    assert body["connections"]
    assert all(tool["connected"] is False for tool in body["connections"])
    assert body["connected_count"] == 0


def test_every_tool_says_why_it_is_locked(client) -> None:  # type: ignore[no-untyped-def]
    """I10 on this surface: a row with no explanation reads as a broken button."""
    for tool in client.get("/onboarding/connections").json()["connections"]:
        assert tool["detail"]
        assert "not connected" in tool["detail"].lower()


# ── Only the customer's own tools ─────────────────────────────


def test_only_customer_connectable_sources_are_offered(client) -> None:  # type: ignore[no-untyped-def]
    offered = {
        tool["source"] for tool in client.get("/onboarding/connections").json()["connections"]
    }

    assert offered == {source.value for source in CONNECTABLE}


@pytest.mark.parametrize("source", NOT_A_CUSTOMER_TOOL, ids=lambda s: s.value)
def test_the_things_a_customer_cannot_connect_are_absent(source: Source) -> None:
    """Each exclusion is a different kind of nonsense, and they are worth naming:

    `HISTORY` is time passing. `OPS_LAYER` is NEXUS's own records, which fill by
    being used. `ONBOARDING` is the wizard the user is standing in. `PAGESPEED`,
    `DATAFORSEO`, `ENRICHMENT` and `TENDER_FEED` are our provider accounts — and two
    are unresolved procurement, so listing them would ask a customer to solve it.
    `LANGUAGE_MODEL` is a deployment-level API key (ADR 0011).
    """
    assert source not in CONNECTABLE


def test_the_option_list_and_the_endpoint_offer_the_same_tools() -> None:
    """`tools_available` is what gets stored; the endpoint is what gets rendered.
    They must not drift, or the user reads about one set and answers another."""
    assert {c.value for c in CONNECTABLE_TOOLS} == {s.value for s in CONNECTABLE}


def test_every_connectable_source_has_a_name() -> None:
    """A `KeyError` at import time is the intended failure for an unnamed source,
    rather than a blank option rendering in the wizard."""
    for source in CONNECTABLE:
        assert TOOL_LABELS[source.value]
        assert LABELS[source]  # the sentence fragment the dashboards use


# ── The counts are derived from the dashboards ────────────────


def test_search_console_unlocks_something(client) -> None:  # type: ignore[no-untyped-def]
    """The regression guard for the defect this step uncovered.

    `Source.SEARCH_CONSOLE` was defined, labelled, and listed in no offering's
    `needs`, so it unlocked nothing — while doc 05 §3.7 says "Rankings need Search
    Console" and §3 counts it among that offering's sources. Offering a tool that
    changes no tile is the same empty promise as a tile with no unlock sentence.
    """
    assert offerings_needing(Source.SEARCH_CONSOLE), "doc 05 §3.7 names it"

    body = client.get("/onboarding/connections").json()
    search_console = next(t for t in body["connections"] if t["source"] == "search_console")
    assert search_console["unlocks"] > 0
    assert search_console["departments"] == ["marketing"]


def test_no_offered_tool_unlocks_nothing(client) -> None:  # type: ignore[no-untyped-def]
    """The general form of the above. If a tool unlocks nothing then either doc 05
    does not need it, in which case do not offer it, or an offering's `needs` is
    missing it — and both are bugs rather than a zero to render."""
    for tool in client.get("/onboarding/connections").json()["connections"]:
        assert tool["unlocks"] > 0, tool["source"]
        assert tool["departments"], tool["source"]


def test_the_counts_match_the_offering_definitions(client) -> None:  # type: ignore[no-untyped-def]
    """Derived, not written down. A hand-maintained number would go stale the first
    time doc 05's spec changed, and nothing would notice."""
    body = client.get("/onboarding/connections").json()

    for tool in body["connections"]:
        source = Source(tool["source"])
        assert tool["unlocks"] == len(offerings_needing(source))


def test_connecting_search_console_would_change_a_real_tile() -> None:
    """The count is only meaningful if the source actually moves a widget's state.

    3.7 is not in `DELIVERED`, so it renders `PLANNED` either way today — which is
    why this asserts on `missing_sources` rather than on the rendered state, and why
    the assertion is about the data rather than the screen.
    """
    seo = next(
        offering
        for director in DIRECTORS
        if director.department is Department.MARKETING
        for offering in director.offerings
        if offering.id == "3.7"
    )

    assert Source.SEARCH_CONSOLE in seo.needs
    # Unbuilt, so still PLANNED. Recorded so the distinction stays visible.
    assert state_for(seo, connected=frozenset(seo.needs)).value == "planned"


# ── The question that records it ──────────────────────────────


def test_the_tools_question_sits_in_its_own_stage() -> None:
    question = BY_KEY["tools_available"]

    assert question.stage is Pass.CONNECT
    assert question.options == CONNECTABLE_TOOLS


def test_the_tools_question_promises_nothing(client) -> None:  # type: ignore[no-untyped-def]
    """Answering must not read as connecting. The `why` is the only place a user
    finds out, so it has to say so rather than implying a connection was made."""
    why = BY_KEY["tools_available"].why.lower()

    assert "nothing is connected" in why
    assert "no connector" in why
