"""`GET /auth/session`, and the logout that has to undo it.

Added because a sign-in UI cannot exist without them. `/auth/me` depends on
`CurrentScope`, which requires an active workspace — so a signed-in person who
has no workspace yet (the normal state between registering and verifying a
domain) could not retrieve even their own identity, and no client could answer
"am I logged in?" after a page reload.

These run hermetically. The endpoint's own logic is what is under test, so the
session and membership lookups are substituted: driving them through a real
database would test the fixture instead of the rule.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.auth.service import Membership, ResolvedSession
from app.deps import current_session
from app.domain.scopes import Department, Role
from app.main import create_app

USER = UUID("11111111-1111-1111-1111-111111111111")
EMAIL = "founder@example.com"
WS_A = UUID("22222222-2222-2222-2222-222222222222")
WS_B = UUID("33333333-3333-3333-3333-333333333333")


def membership(workspace_id: UUID, name: str, role: Role = Role.OWNER) -> Membership:
    return Membership(
        workspace_id=workspace_id,
        tenant_id=uuid4(),
        workspace_name=name,
        role=role,
        departments=frozenset({Department.FINANCE}),
    )


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """A TestClient whose session resolves, with the membership list injectable."""
    memberships: list[Membership] = []

    async def fake_memberships(db: object, *, user_id: UUID) -> list[Membership]:
        return list(memberships)

    async def fake_email(db: object, user_id: UUID) -> str:
        """Substituted for the same reason the membership lookup is.

        The endpoint reports the caller's own address since finding F8 — before
        it, `/account` had only a UUID to render on the one page that promises
        everything is read from the API. Where the string comes from is
        `app_user`; that it is *returned* is what these tests are about.
        """
        return EMAIL

    @asynccontextmanager
    async def fake_db() -> AsyncIterator[None]:
        """The handler opens a session before it queries, so patching only the
        query still demands a database. Both have to go."""
        yield None

    # Patched where they are used, not where they are defined.
    monkeypatch.setattr("app.routes.auth.memberships_for_user", fake_memberships)
    monkeypatch.setattr("app.routes.auth._email_for", fake_email)
    monkeypatch.setattr("app.routes.auth._unscoped_session", fake_db)

    app = create_app()

    def make(active: UUID | None) -> TestClient:
        async def fake_session() -> ResolvedSession:
            return ResolvedSession(session_id=uuid4(), user_id=USER, active_workspace_id=active)

        app.dependency_overrides[current_session] = fake_session
        return TestClient(app)

    yield make, memberships
    app.dependency_overrides.clear()


# ── The reason the endpoint exists ────────────────────────────


def test_a_user_with_no_workspace_can_still_read_their_own_account(signed_in) -> None:  # type: ignore[no-untyped-def]
    """The state every account is in immediately after registering.

    `/auth/me` returns 403 here, correctly — it hands back workspace authority
    and there is none. But a client still has to be able to render a signed-in
    page, and this is what lets it.
    """
    make, memberships = signed_in
    memberships.clear()

    response = make(None).get("/auth/session")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(USER)
    assert body["workspaces"] == []
    assert body["active_workspace_id"] is None


def test_me_still_refuses_the_same_caller(signed_in) -> None:  # type: ignore[no-untyped-def]
    """The new endpoint must not have weakened the old one.

    If `/me` started answering without a workspace, every caller downstream of it
    would receive a scope built from nothing.
    """
    make, memberships = signed_in
    memberships.clear()

    assert make(None).get("/auth/me").status_code in {401, 403}


def test_memberships_are_reported_with_their_roles(signed_in) -> None:  # type: ignore[no-untyped-def]
    make, memberships = signed_in
    memberships[:] = [
        membership(WS_A, "Alpha", Role.OWNER),
        membership(WS_B, "Beta", Role.CONTRIBUTOR),
    ]

    body = make(WS_A).get("/auth/session").json()

    assert {w["name"] for w in body["workspaces"]} == {"Alpha", "Beta"}
    by_id = {w["workspace_id"]: w["role"] for w in body["workspaces"]}
    assert by_id[str(WS_A)] == "owner"
    assert by_id[str(WS_B)] == "contributor"
    assert body["active_workspace_id"] == str(WS_A)


# ── The stale pointer ─────────────────────────────────────────


def test_a_revoked_active_workspace_is_not_reported_as_active(signed_in) -> None:  # type: ignore[no-untyped-def]
    """A membership can be revoked while a session is live (doc 06 §4.15).

    The session row still points at the old workspace. Reporting that pointer
    verbatim would leave the client showing an active workspace that
    `current_scope` refuses on the very next request — a UI stuck insisting it is
    somewhere it cannot go, with no way to explain why.
    """
    make, memberships = signed_in
    memberships[:] = [membership(WS_B, "Still a member")]

    body = make(WS_A).get("/auth/session").json()  # pointer at a workspace now gone

    assert body["active_workspace_id"] is None, "a stale pointer must not be echoed back"
    assert [w["name"] for w in body["workspaces"]] == ["Still a member"]


def test_the_pointer_is_not_treated_as_a_membership(signed_in) -> None:  # type: ignore[no-untyped-def]
    """The pointer must never be able to conjure access on its own.

    It comes from the session row, and this endpoint deliberately does not join
    it to anything — the membership list is the only source of truth about what
    the caller belongs to.
    """
    make, memberships = signed_in
    memberships.clear()

    body = make(WS_A).get("/auth/session").json()

    assert body["workspaces"] == []
    assert body["active_workspace_id"] is None


# ── No session ────────────────────────────────────────────────


def test_no_cookie_is_401_not_403(client_no_auth: TestClient) -> None:
    """401 means "authenticate", 403 means "you cannot". A sign-in UI branches on
    the difference: one sends you to the form, the other explains a limit."""
    assert client_no_auth.get("/auth/session").status_code == 401


@pytest.fixture
def client_no_auth() -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client


# ── Logout clears both cookies ────────────────────────────────


def test_logout_clears_the_csrf_cookie_as_well_as_the_session(
    client_no_auth: TestClient,
) -> None:
    """The session cookie is httponly, so the readable CSRF cookie is the only
    signed-in signal a client can see. One surviving logout leaves every client
    believing a revoked session is still live.

    Goes through the real double-submit gate — cookie set, matching header sent.
    An earlier version sent the header with no cookie, which worked only because
    `require_csrf` returned early on an absent cookie. That fail-open is now a
    403, so this test would have been asserting against a hole rather than
    through it.

    No session cookie is needed: the handler skips the database when there is
    none and still clears both cookies, which is the case where a cookie
    outlived its session row.
    """
    token = "a-known-csrf-value"
    client_no_auth.cookies.set(CSRF_COOKIE_NAME, token)

    response = client_no_auth.post("/auth/logout", headers={CSRF_HEADER_NAME: token})

    assert response.status_code == 204

    joined = " ".join(response.headers.get_list("set-cookie"))
    assert "nexus_session=" in joined, "session cookie not cleared"
    assert f"{CSRF_COOKIE_NAME}=" in joined, "CSRF cookie not cleared"
    # Deletion is expressed as an immediate expiry, not an omission.
    assert joined.count("Max-Age=0") >= 2 or joined.count("expires=") >= 2


def test_logout_without_a_csrf_cookie_is_refused(client_no_auth: TestClient) -> None:
    """The companion to the above, and the reason it had to change.

    A caller holding a session but missing its CSRF cookie is the cookie-eviction
    scenario `app/auth/csrf.py` exists for. It used to be waved through.
    """
    assert client_no_auth.post("/auth/logout").status_code == 403


def test_the_session_reports_the_caller_s_email(signed_in) -> None:  # type: ignore[no-untyped-def]
    """Finding F8. The page that renders this had only a UUID to show.

    `/account` promises *"everything below is read from the API"*, and that was
    exactly the problem: the session response carried no email, so the screen
    identified a person by `12af801a-dd42-…` and their company by a second UUID
    — with the company's actual name in the row directly beneath.

    It discloses nothing new. This endpoint already requires that person's own
    session cookie, and the address is the one they signed in with.
    """
    make, memberships = signed_in
    memberships.clear()

    body = make(None).get("/auth/session").json()

    assert body["email"] == EMAIL, "the session no longer reports who the caller is"
