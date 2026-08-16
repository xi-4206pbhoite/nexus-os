"""CSRF protection, double-submit cookie.

`SameSite=Lax` on the session cookie already blocks cross-site form POSTs in
current browsers, and it is the primary defence. This is the second layer,
because "current browsers" is doing real work in that sentence: Lax is a
browser-enforced policy, and a bug, an old client or a same-site subdomain
takeover all bypass it.

The scheme: a random value is set in a **readable** cookie at login, and
state-changing requests must echo it in the `X-CSRF-Token` header. An attacker
on another origin can cause the browser to *send* the cookie but cannot read it,
so they cannot produce the matching header.

Safe methods are exempt. If a GET changes state, that is the bug — not this.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Header, HTTPException, Request, status

from app.auth.tokens import csrf_matches

CSRF_COOKIE_NAME = "nexus_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


async def require_csrf(
    request: Request,
    nexus_csrf: Annotated[str | None, Cookie(alias=CSRF_COOKIE_NAME)] = None,
    x_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> None:
    """Reject a state-changing request whose header does not match its cookie."""
    if request.method in SAFE_METHODS:
        return

    # No CSRF cookie means no authenticated session to protect; the session
    # dependency will reject it on its own terms.
    if nexus_csrf is None:
        return

    if not csrf_matches(nexus_csrf, x_csrf_token):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Missing or invalid {CSRF_HEADER_NAME}",
        )
