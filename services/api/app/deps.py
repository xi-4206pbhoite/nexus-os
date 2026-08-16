"""Request dependencies.

The single place a `ScopedSession` is constructed. Everything downstream
receives it; nothing downstream constructs one.

Note what is *not* here: there is no `X-Workspace` header, no `workspace_id`
query parameter, no body field. Doc 06 §2.1 requires the active workspace to be
resolved server-side per request, because claim-based row-level security assumes
one tenant per session and a client-controlled switcher breaks that assumption.
The active workspace therefore lives in the `user_session` row and is read from
there, every request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.auth.service import (
    build_scope,
    memberships_for_user,
    resolve_session,
)
from app.config import Settings, get_settings
from app.db import _unscoped_session
from app.domain.session import ScopedSession
from app.logging import user_id_var, workspace_id_var


async def current_scope(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    nexus_session: Annotated[str | None, Cookie(alias="nexus_session")] = None,
) -> ScopedSession:
    """Resolve the caller's authority, or 401/403.

    Failure modes are kept distinct where it is safe to do so:

    - no or invalid cookie          -> 401, "authenticate"
    - authenticated, no workspace   -> 403, "no workspace selected"
    - authenticated, workspace gone -> 403, and the stale pointer is not trusted

    The last case matters: a membership can be revoked while a session is live
    (doc 06 §4.15 — role change is immediate). The session's stored workspace
    pointer is therefore re-validated against current memberships on every
    request rather than trusted because it was valid at login.
    """
    if not nexus_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    async with _unscoped_session() as db:
        resolved = await resolve_session(db, token=nexus_session)
        if resolved is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

        memberships = await memberships_for_user(db, user_id=resolved.user_id)

    if not memberships:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No workspace membership")

    if resolved.active_workspace_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No workspace selected")

    membership = next(
        (m for m in memberships if m.workspace_id == resolved.active_workspace_id),
        None,
    )
    if membership is None:
        # The pointer is stale — access was revoked since it was set. Do not
        # silently fall back to another workspace; that would be a surprising
        # cross-workspace action taken on the user's behalf.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Workspace access revoked")

    scope = build_scope(user_id=resolved.user_id, membership=membership)

    # Bind to the log context so every line in this request carries them.
    request.state.scope = scope
    user_id_var.set(str(scope.user_id))
    workspace_id_var.set(str(scope.workspace_id))
    return scope


CurrentScope = Annotated[ScopedSession, Depends(current_scope)]


def require_executive_surface(scope: CurrentScope) -> ScopedSession:
    """Doc 06 §2.4 — Executive surface is Owner and Executive only at MVP.

    A Department Manager's portal is six directors, not seven: no Chief of
    Staff page, no Morning Brief, no composite score.
    """
    if not scope.can_see_executive_surface:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The executive surface requires an Owner or Executive role",
        )
    return scope
