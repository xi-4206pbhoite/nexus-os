"""Registration ends in a session, and what that costs.

Doc 07's process rule is to write the test that proves the invariant before the
feature it guards. The invariant here is unusual because this change *gives one
up*, so the tests pin down exactly how much:

**What is kept.** A taken address with the wrong password returns login's status
and login's wording, byte for byte. So an attacker reading responses cannot tell
"already registered under another password" apart from "no such account" — the two
answers are identical, and `test_the_refusal_is_indistinguishable_from_login`
asserts it against the real constant rather than a copy of the string.

**What is lost.** A *new* address returns 201 with a session; a taken one with the
wrong password returns 401. That difference is an enumeration oracle and cannot be
hidden while registration also signs you in (ADR 0014). It is not tested for
absence, because it is present.

**Why it was worth it.** Before this, registration returned `check_your_email`
whether or not the address existed, no email was ever sent, and no password reset
existed. Re-registering with a different password silently did nothing and the
first password still stood, so the account was unreachable — reproduced against a
live API before any of this was written.

Hermetic: the point is which decisions the handler makes, so the session and
account lookups are substituted. `test_auth_flow.py` proves the database
behaviours these sit on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.service import AuthError, EmailAlreadyRegisteredError, IssuedSession, Membership
from app.config import Env
from app.domain.scopes import Department, Role
from app.main import create_app

USER = UUID("11111111-1111-1111-1111-111111111111")
WORKSPACE = UUID("22222222-2222-2222-2222-222222222222")
EMAIL = "founder@acme.com"
PASSWORD = "a-long-enough-password"

TAKEN = "taken@acme.com"
"""Registered already, under a different password."""


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[str]]]:
    """A client with the account store substituted.

    `calls` records what the handler did, so a test can assert that a duplicate
    address still went through `authenticate` rather than being waved through.
    """
    calls: list[str] = []
    memberships: list[Membership] = []

    async def fake_create_workspace(db: object, **kwargs: object) -> UUID:
        calls.append("create_workspace")
        # A real creation makes the caller a member, so the fake must too, or
        # `_sign_in` reads the pre-creation membership list and auto-selects
        # nothing — which is the bug this whole phase exists to remove.
        memberships.append(
            Membership(
                workspace_id=WORKSPACE,
                tenant_id=uuid4(),
                workspace_name="acme.com",
                role=Role.OWNER,
                departments=frozenset({Department.EXECUTIVE}),
            )
        )
        return WORKSPACE

    async def fake_register(db: object, **kwargs: object) -> UUID:
        calls.append("register_user")
        if kwargs.get("email") == TAKEN:
            raise EmailAlreadyRegisteredError(TAKEN)
        return USER

    async def fake_authenticate(db: object, *, email: str, password: str) -> UUID:
        calls.append("authenticate")
        if email == TAKEN and password != PASSWORD:
            raise AuthError("invalid credentials")
        return USER

    async def fake_memberships(db: object, *, user_id: UUID) -> list[Membership]:
        return list(memberships)

    async def fake_issue(db: object, **kwargs: object) -> IssuedSession:
        from datetime import UTC, datetime, timedelta

        return IssuedSession(
            token="a-session-token",
            session_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    @asynccontextmanager
    async def fake_db() -> AsyncIterator[object]:
        class Session:
            async def commit(self) -> None:
                return None

        yield Session()

    for name, value in (
        ("create_workspace_at_registration", fake_create_workspace),
        ("register_user", fake_register),
        ("authenticate", fake_authenticate),
        ("memberships_for_user", fake_memberships),
        ("issue_session", fake_issue),
        ("_unscoped_session", fake_db),
    ):
        monkeypatch.setattr(f"app.routes.auth.{name}", value)

    with TestClient(create_app()) as client:
        yield client, calls


def post(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> object:
    return client.post("/auth/register", json={"email": email, "password": password})


# ── Registration signs you in ─────────────────────────────────


def test_registering_returns_a_session_not_a_promise_of_email(api) -> None:  # type: ignore[no-untyped-def]
    """The old body was `{"status": "check_your_email"}` and no email was sent."""
    client, _ = api
    response = post(client)

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(USER)
    assert "status" not in body, "the check-your-email shape is gone, not merely unused"


def test_registering_sets_the_session_and_csrf_cookies(api) -> None:  # type: ignore[no-untyped-def]
    """Without both, the caller is not actually signed in.

    The session cookie authenticates; the readable CSRF companion is the only
    signal a browser client can see, and every state-changing call must echo it.
    """
    client, _ = api
    post(client)

    assert client.cookies.get("nexus_session") is not None
    assert client.cookies.get("nexus_csrf") is not None


def test_a_duplicate_address_with_the_right_password_signs_in(api) -> None:  # type: ignore[no-untyped-def]
    """Re-submitting the form is idempotent, which is what a retry deserves."""
    client, calls = api
    response = post(client, email=TAKEN, password=PASSWORD)

    assert response.status_code == 201
    assert response.json()["user_id"] == str(USER)
    assert calls[:2] == ["register_user", "authenticate"], (
        "the duplicate must still prove the password, not be waved through"
    )


# ── A workspace, so registration completes into something usable ──


def test_registering_creates_a_workspace_and_selects_it(api) -> None:  # type: ignore[no-untyped-def]
    """ADR 0013. Without this, registration ends in a 403 on every screen.

    `active_workspace_id` matters as much as the workspace: it is resolved
    server-side from `user_session`, so a workspace that exists but is not selected
    is still a dead end — which is exactly the state the old flow left people in
    after they signed in.
    """
    client, calls = api
    body = post(client).json()

    assert "create_workspace" in calls
    assert [w["workspace_id"] for w in body["workspaces"]] == [str(WORKSPACE)]
    assert body["workspaces"][0]["role"] == "owner"
    assert body["active_workspace_id"] == str(WORKSPACE), (
        "created before the session is issued, so _sign_in auto-selects it"
    )


def test_an_existing_member_does_not_collect_a_second_workspace(api) -> None:  # type: ignore[no-untyped-def]
    """Registration doubles as the idempotent re-submit path, so the guard is on
    holding no membership rather than on having just created the account."""
    client, calls = api

    post(client)
    first = calls.count("create_workspace")
    post(client)

    assert first == 1
    assert calls.count("create_workspace") == 1, "a resubmit must not mint another workspace"


def test_a_duplicate_address_with_a_wrong_password_is_refused(api) -> None:  # type: ignore[no-untyped-def]
    client, _ = api
    response = post(client, email=TAKEN, password="not-the-right-password")

    assert response.status_code == 401
    assert client.cookies.get("nexus_session") is None, "a refusal must not mint a session"


def test_the_refusal_is_indistinguishable_from_login(api) -> None:  # type: ignore[no-untyped-def]
    """The one property this change keeps, so it is asserted rather than assumed.

    Both paths must answer identically, or registration becomes a *better* oracle
    than login: it would separate "exists under another password" from "does not
    exist", which login deliberately refuses to do.
    """
    client, _ = api

    registered = post(client, email=TAKEN, password="not-the-right-password")
    signed_in = client.post("/auth/login", json={"email": TAKEN, "password": "wrong-as-well"})

    assert registered.status_code == signed_in.status_code == 401
    assert registered.json()["detail"] == signed_in.json()["detail"]


def test_registration_is_not_csrf_guarded(api) -> None:  # type: ignore[no-untyped-def]
    """An anonymous visitor has no CSRF cookie yet. Requiring one here would make
    it impossible to create an account at all."""
    client, _ = api
    assert post(client).status_code == 201


# ── The local-only password reset ─────────────────────────────


@pytest.mark.parametrize("env", [Env.staging, Env.production])
def test_the_dev_reset_does_not_exist_outside_local(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """404, not 403.

    A 403 would confirm that a route which sets arbitrary passwords with no proof
    of ownership is deployed — worth more to an attacker than the refusal costs
    them. Same reasoning `routes/dashboards.py` applies to a department the caller
    does not hold.
    """
    from app.config import get_settings

    monkeypatch.setenv("NEXUS_ENV", env.value)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/auth/dev/reset-password",
                json={"email": EMAIL, "password": "a-brand-new-password"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404


def test_the_dev_reset_is_reachable_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    """It has to work, or a locked-out development account stays locked out."""
    changed: list[str] = []

    async def fake_set_password(db: object, *, email: str, password: str) -> bool:
        changed.append(email)
        return True

    @asynccontextmanager
    async def fake_db() -> AsyncIterator[object]:
        class Session:
            async def commit(self) -> None:
                return None

        yield Session()

    monkeypatch.setattr("app.routes.auth.set_password", fake_set_password)
    monkeypatch.setattr("app.routes.auth._unscoped_session", fake_db)

    with TestClient(create_app()) as client:
        response = client.post(
            "/auth/dev/reset-password",
            json={"email": EMAIL, "password": "a-brand-new-password"},
        )

    assert response.status_code == 204
    assert changed == [EMAIL]


def test_the_dev_reset_says_when_no_such_account_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """A development tool that silently no-ops on a typo'd address is the
    confusion it was built to end."""

    async def fake_set_password(db: object, *, email: str, password: str) -> bool:
        return False

    @asynccontextmanager
    async def fake_db() -> AsyncIterator[object]:
        class Session:
            async def commit(self) -> None:
                return None

        yield Session()

    monkeypatch.setattr("app.routes.auth.set_password", fake_set_password)
    monkeypatch.setattr("app.routes.auth._unscoped_session", fake_db)

    with TestClient(create_app()) as client:
        response = client.post(
            "/auth/dev/reset-password",
            json={"email": "nobody@acme.com", "password": "a-brand-new-password"},
        )

    assert response.status_code == 404
    assert "account" in response.json()["detail"].lower()


def test_the_dev_reset_still_enforces_password_length() -> None:
    """Being a development tool is not a reason to write a password the real
    validator would reject — the account would then be unusable a different way."""
    with TestClient(create_app()) as client:
        response = client.post(
            "/auth/dev/reset-password", json={"email": EMAIL, "password": "short"}
        )

    assert response.status_code == 422
