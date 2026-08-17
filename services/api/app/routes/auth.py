"""Authentication routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.auth.csrf import CSRF_COOKIE_NAME, require_csrf
from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
)
from app.auth.service import (
    AuthError,
    EmailAlreadyRegisteredError,
    authenticate,
    issue_session,
    memberships_for_user,
    register_user,
    resolve_session,
    revoke_session,
    set_active_workspace,
)
from app.auth.tokens import new_csrf_token
from app.config import Settings, get_settings
from app.db import _unscoped_session
from app.deps import CurrentScope, CurrentSession
from app.logging import get_logger

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class WorkspaceSummary(BaseModel):
    workspace_id: UUID
    name: str
    role: str


class SessionResponse(BaseModel):
    user_id: UUID
    workspaces: list[WorkspaceSummary]
    active_workspace_id: UUID | None


def _set_session_cookie(response: Response, token: str, settings: Settings) -> str:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,  # not reachable from JavaScript, so XSS cannot exfiltrate it
        secure=not settings.is_local,  # plain HTTP only in local development
        samesite="lax",  # blocks cross-site POSTs while keeping normal navigation
        path="/",
    )

    # Double-submit companion. Deliberately readable by JavaScript — the client
    # must be able to echo it into a header, which is precisely what a
    # cross-origin attacker cannot do.
    csrf = new_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf,
        max_age=settings.session_max_age_seconds,
        httponly=False,
        secure=not settings.is_local,
        samesite="lax",
        path="/",
    )
    return csrf


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Create an account.

    Returns the same response whether or not the email was already registered.
    A distinct "already registered" reply is a membership oracle: it confirms
    which addresses hold accounts here. Verification email delivery (M3) is what
    tells the real owner what happened.
    """
    try:
        async with _unscoped_session() as db:
            await register_user(
                db,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name,
            )
            await db.commit()
    except EmailAlreadyRegisteredError:
        log.info("auth.register.duplicate")
    except WeakPasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return {"status": "check_your_email"}


@router.post("/login", response_model=SessionResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    async with _unscoped_session() as db:
        try:
            user_id = await authenticate(db, email=payload.email, password=payload.password)
        except AuthError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from exc

        memberships = await memberships_for_user(db, user_id=user_id)
        # Only auto-select when there is no ambiguity. Picking one of several on
        # the user's behalf risks acting in the wrong client's workspace.
        active = memberships[0].workspace_id if len(memberships) == 1 else None

        issued = await issue_session(
            db,
            user_id=user_id,
            ttl_seconds=settings.session_max_age_seconds,
            active_workspace_id=active,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()

    _set_session_cookie(response, issued.token, settings)
    log.info("auth.login", workspace_count=len(memberships))

    return SessionResponse(
        user_id=user_id,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=active,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    settings: Annotated[Settings, Depends(get_settings)],
    nexus_session: Annotated[str | None, Cookie(alias="nexus_session")] = None,
) -> Response:
    if nexus_session:
        async with _unscoped_session() as db:
            resolved = await resolve_session(db, token=nexus_session)
            if resolved is not None:
                await revoke_session(db, session_id=resolved.session_id)
                await db.commit()

    # Cookies are cleared on the response that is actually returned.
    #
    # This used to call `delete_cookie` on an injected `response: Response` and
    # then `return Response(...)`. FastAPI only merges the injected response's
    # headers when the handler returns *data*; returning a Response replaces it
    # outright, so both deletions were silently discarded and the browser kept
    # sending a cookie for a session that had been revoked server-side. The
    # revocation always worked, which is why nothing caught it — the session was
    # genuinely dead, but no client could tell.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie_name, path="/")
    # The CSRF companion goes too. The session cookie is httponly, so the
    # readable CSRF cookie is the only signed-in signal a client can see; one
    # surviving logout leaves every client believing a dead session is live.
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return response


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: UUID


@router.post(
    "/workspace",
    response_model=SessionResponse,
    dependencies=[Depends(require_csrf)],
)
async def switch_workspace(
    payload: SwitchWorkspaceRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    nexus_session: Annotated[str | None, Cookie(alias="nexus_session")] = None,
) -> SessionResponse:
    """Change the active workspace.

    The requested workspace is checked against the caller's *current*
    memberships before it is stored. A workspace id in a request body is
    untrusted input — this endpoint is the one place a client may express a
    preference, and it is validated rather than believed.

    Doc 06 §2.1 also requires agent sessions to be torn down and caches
    invalidated on switch. Neither exists yet; the teardown hook is called here
    so the obligation is visible in code rather than remembered later.
    """
    if not nexus_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    async with _unscoped_session() as db:
        resolved = await resolve_session(db, token=nexus_session)
        if resolved is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

        memberships = await memberships_for_user(db, user_id=resolved.user_id)
        target = next((m for m in memberships if m.workspace_id == payload.workspace_id), None)
        if target is None:
            # Deliberately identical to "does not exist": confirming that a
            # workspace exists but is not yours is an existence disclosure
            # (doc 06 §4.5).
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No such workspace")

        await set_active_workspace(
            db, session_id=resolved.session_id, workspace_id=target.workspace_id
        )
        await db.commit()

    await _teardown_on_switch(resolved.session_id)
    log.info("auth.workspace.switch")

    return SessionResponse(
        user_id=resolved.user_id,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=target.workspace_id,
    )


async def _teardown_on_switch(session_id: UUID) -> None:
    """Doc 06 §2.1 — agent sessions are torn down and never reused across
    workspaces, and every scope-keyed cache entry is dropped.

    Agents arrive in M12 and the cache in M6/M8. This is the seam they attach
    to: a switch must not be able to ship without teardown, so the call site
    exists before the things it tears down.
    """
    log.info("auth.workspace.teardown", session_id=str(session_id))


@router.get("/session", response_model=SessionResponse)
async def session_state(resolved: CurrentSession) -> SessionResponse:
    """The caller's own account, whether or not they have a workspace.

    `/me` cannot answer this. It depends on `CurrentScope`, which requires an
    active workspace — correctly, because it hands back the authority used to
    reach workspace data. But that leaves a signed-in person with no workspace
    unable to retrieve even their own identity, so a client had no way to answer
    "am I logged in?" after a page reload. Every sign-in UI needs that.

    Returns exactly what `/login` returns, from the session cookie rather than
    from credentials. It discloses nothing new: the same user, the same
    memberships, read under the `membership_own_rows` policy that restricts the
    query to the caller's own rows.
    """
    async with _unscoped_session() as db:
        memberships = await memberships_for_user(db, user_id=resolved.user_id)

    # The session's pointer, reported only if it still corresponds to a live
    # membership. A revoked membership must not leave the client believing it has
    # an active workspace; `current_scope` would refuse the next real request and
    # the UI would have no idea why.
    known = {m.workspace_id for m in memberships}
    active = resolved.active_workspace_id if resolved.active_workspace_id in known else None

    return SessionResponse(
        user_id=resolved.user_id,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=active,
    )


@router.get("/me", response_model=SessionResponse)
async def me(scope: CurrentScope) -> SessionResponse:
    async with _unscoped_session() as db:
        memberships = await memberships_for_user(db, user_id=scope.user_id)

    return SessionResponse(
        user_id=scope.user_id,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=scope.workspace_id,
    )
