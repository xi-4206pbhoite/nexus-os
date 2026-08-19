"""Authentication routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.csrf import CSRF_COOKIE_NAME, require_csrf
from app.auth.domains import create_workspace_at_registration
from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
)
from app.auth.service import (
    AuthError,
    EmailAlreadyRegisteredError,
    Membership,
    authenticate,
    issue_session,
    memberships_for_user,
    register_user,
    resolve_session,
    revoke_session,
    set_active_workspace,
    set_password,
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


async def _sign_in(
    db: AsyncSession,
    *,
    user_id: UUID,
    request: Request,
    settings: Settings,
    memberships: list[Membership] | None = None,
) -> tuple[str, SessionResponse]:
    """Mint a session for an already-authenticated user, and commit.

    Shared by `login` and `register` so there is one place that decides what a
    fresh session looks like — including the auto-select rule, which is a security
    decision rather than a convenience: picking one of several workspaces on the
    user's behalf risks acting in the wrong client's workspace (the agency case
    doc 06 §2.1 is built around).

    `memberships` is accepted so a caller that has already read them does not pay
    for a second round trip. Registration had been querying them twice — once to
    decide whether to create a workspace, once here — and on a managed database an
    ocean away each read is real time on a request that already makes several.

    Returns the raw token rather than setting the cookie, because the caller owns
    the response object.
    """
    if memberships is None:
        memberships = await memberships_for_user(db, user_id=user_id)
    active = memberships[0].workspace_id if len(memberships) == 1 else None

    issued = await issue_session(
        db,
        user_id=user_id,
        ttl_seconds=settings.session_max_age_seconds,
        active_workspace_id=active,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()

    return issued.token, SessionResponse(
        user_id=user_id,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=active,
    )


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    """Create an account and sign straight in.

    **This deliberately trades away a security property, and the trade is
    recorded in ADR 0014 rather than made quietly here.**

    Registration used to answer `{"status": "check_your_email"}` for every
    request, identical whether or not the address was taken, so the endpoint could
    not be used to discover who holds an account. That property cannot survive a
    registration that ends in a usable session: a new address yields one and a
    taken address with the wrong password cannot, and no amount of care hides the
    difference. Every mainstream product accepts this; the compensating control is
    login rate limiting, which is open as **D14** and is owed before this surface
    is public.

    What it buys is the flow working at all. There is no email delivery and no
    password reset, so the previous behaviour meant a re-registration with a
    different password silently did nothing, the first password still stood, and
    the account was unreachable. That was reproduced before this was changed.

    The duplicate case is not special-cased into a friendly message. It falls
    through to `authenticate`, so re-registering with the *same* password signs
    you in — idempotent, which is what a user retrying a form actually wants — and
    a wrong password gets login's exact wording, not a hint that the address
    exists.
    """
    async with _unscoped_session() as db:
        # One transaction for the whole of registration, deliberately. The account
        # insert used to commit on its own, which meant a later failure could leave
        # an account with no workspace — the exact dead end ADR 0013 removes,
        # recreated by a partial write. Now it either all happens or none of it
        # does, and it costs one fewer round trip.
        try:
            await register_user(
                db,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name,
            )
        except EmailAlreadyRegisteredError:
            # Not an error path. The caller still has to prove the password below.
            log.info("auth.register.duplicate")
        except WeakPasswordError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

        try:
            # Sees the uncommitted insert above: same transaction, same session.
            user_id = await authenticate(db, email=payload.email, password=payload.password)
        except AuthError as exc:
            # Reached only when the address was already registered under a
            # different password. Same status and same wording as `login`, so the
            # two are indistinguishable to anything reading responses.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from exc

        # A workspace, or registration completes into a 403 (ADR 0013). Created
        # before the session is issued so the membership list below has exactly one
        # entry and gets auto-selected — no switch call, and no window in which the
        # caller is signed in with nowhere to go.
        #
        # Guarded on holding none, not on having just registered: this route is also
        # the idempotent re-registration path, and an existing member must not
        # collect a second workspace every time they resubmit the form.
        memberships = await memberships_for_user(db, user_id=user_id)
        if not memberships:
            await create_workspace_at_registration(db, user_id=user_id, email=payload.email)
            memberships = await memberships_for_user(db, user_id=user_id)

        token, session = await _sign_in(
            db,
            user_id=user_id,
            request=request,
            settings=settings,
            memberships=memberships,
        )

    _set_session_cookie(response, token, settings)
    log.info("auth.register.signed_in", workspace_count=len(session.workspaces))
    return session


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

        # Auto-select and session minting live in `_sign_in`, shared with
        # `register`, so the two cannot drift apart.
        token, session = await _sign_in(db, user_id=user_id, request=request, settings=settings)

    _set_session_cookie(response, token, settings)
    log.info("auth.login", workspace_count=len(session.workspaces))
    return session


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


class DevResetRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


@router.post("/dev/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def dev_reset_password(
    payload: DevResetRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Set a password without proving ownership of the address. **Local only.**

    There is no real password-reset flow yet, and until there is, a mistyped
    password on an account with no email delivery is a permanently unreachable
    account. This is the developer's way out of that, and nothing more.

    **It refuses to exist outside local and CI**, with a 404 rather than a 403 —
    the same reasoning `routes/dashboards.py` applies to a department the caller
    does not hold. A 403 would confirm that a route which sets arbitrary passwords
    is deployed, which is worth more to an attacker than the refusal costs them.

    The refusal is the same shape as `app/embedding/registry.py`'s: an environment
    that must never run this does not get a warning it can ignore, it gets a
    closed door.
    """
    if not settings.is_local:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    async with _unscoped_session() as db:
        try:
            changed = await set_password(db, email=payload.email, password=payload.password)
        except WeakPasswordError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        await db.commit()

    # Reported, because this is a development tool and a silent no-op on a typo'd
    # address is exactly the confusion it exists to end.
    log.warning("auth.dev.password_reset", account_found=changed, env=settings.env.value)
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that address.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
