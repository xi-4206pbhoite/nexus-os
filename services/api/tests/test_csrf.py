"""CSRF double-submit, and the cookie flags the session depends on."""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_state_changing_request_without_the_header_is_rejected(client: TestClient) -> None:
    """The browser will send the cookie; only the real origin can read it."""
    client.cookies.set(CSRF_COOKIE_NAME, "a-known-csrf-value")
    client.cookies.set("nexus_session", "irrelevant-here")

    response = client.post("/auth/logout")
    assert response.status_code == 403
    assert CSRF_HEADER_NAME in response.json()["detail"]


def test_mismatched_header_is_rejected(client: TestClient) -> None:
    client.cookies.set(CSRF_COOKIE_NAME, "a-known-csrf-value")
    client.cookies.set("nexus_session", "irrelevant-here")

    response = client.post("/auth/logout", headers={CSRF_HEADER_NAME: "not-the-same"})
    assert response.status_code == 403


async def test_matching_header_passes_the_csrf_gate() -> None:
    """Exercised directly rather than through a route.

    A route would carry on into the database, and the hermetic fixture
    deliberately withholds one — so going through the route would test the
    fixture, not the gate.
    """
    from app.auth.csrf import require_csrf

    request = Request({"type": "http", "method": "POST", "headers": [], "query_string": b""})
    # Returns None rather than raising: the gate is satisfied.
    assert (
        await require_csrf(
            request, nexus_csrf="a-known-csrf-value", x_csrf_token="a-known-csrf-value"
        )
        is None
    )


async def test_absent_csrf_cookie_defers_to_the_session_check() -> None:
    """No CSRF cookie means no authenticated session for CSRF to protect.

    Rejecting here would turn every unauthenticated POST — including login —
    into a 403 about the wrong thing.
    """
    from app.auth.csrf import require_csrf

    request = Request({"type": "http", "method": "POST", "headers": [], "query_string": b""})
    assert await require_csrf(request, nexus_csrf=None, x_csrf_token=None) is None


def test_safe_methods_are_exempt(client: TestClient) -> None:
    """If a GET changes state, that is the bug — not this."""
    client.cookies.set(CSRF_COOKIE_NAME, "a-known-csrf-value")
    response = client.get("/health")
    assert response.status_code == 200


def test_login_sets_httponly_session_and_readable_csrf_cookie() -> None:
    """The two cookies have deliberately opposite visibility.

    The session cookie must be unreadable by JavaScript so XSS cannot exfiltrate
    it. The CSRF cookie must be readable, because the client has to echo it into
    a header — which is exactly what a cross-origin attacker cannot do.
    """
    from fastapi import Response

    from app.config import get_settings
    from app.routes.auth import _set_session_cookie

    response = Response()
    csrf = _set_session_cookie(response, "a-session-token", get_settings())

    headers = [v for k, v in response.raw_headers if k == b"set-cookie"]
    decoded = [h.decode() for h in headers]

    session_cookie = next(c for c in decoded if c.startswith("nexus_session="))
    csrf_cookie = next(c for c in decoded if c.startswith(f"{CSRF_COOKIE_NAME}="))

    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in session_cookie.lower() or "samesite=lax" in session_cookie.lower()
    assert csrf in csrf_cookie
