"""Authentication routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, EmailStr, Field

from app.auth import password_reset
from app.auth.csrf import CSRF_COOKIE_NAME, require_csrf
from app.auth.email_verification import build_email as build_verification_email
from app.auth.email_verification import issue as issue_verification
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
)
from app.auth.tokens import new_csrf_token
from app.config import Settings, get_settings
from app.db import _unscoped_session
from app.deps import CurrentScope, CurrentSession
from app.logging import get_logger
from app.mail import Email, Mailer, build_mailer

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
        secure=settings.cookies_secure,  # plain HTTP only in local and ci
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
        secure=settings.cookies_secure,
        samesite="lax",
        path="/",
    )
    return csrf


def _send_later(background: BackgroundTasks, mailer: Mailer, message: Email) -> None:
    """Queue a message so the response does not wait for the transport.

    This is a security property, not a latency optimisation. If the send happens
    inline, a request for an address that has an account takes an SMTP
    round-trip longer than one that does not — and both of the endpoints below
    are built on the premise that a caller cannot tell those apart. Identical
    bodies do not help if the clock answers the question.
    """
    background.add_task(mailer.send, message)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Create an account and send the verification email.

    Returns the same response whether or not the email was already registered.
    A distinct "already registered" reply is a membership oracle: it confirms
    which addresses hold accounts here.

    **Delivery is what makes that safe rather than merely quiet.** Until P3 there
    was no email, so the same-response rule protected the address at the cost of
    telling nobody anything — and `email_verified_at` could never be set, which
    left the EMAIL domain-verification method structurally dead. The real owner
    now learns what happened, including that somebody else tried to register
    their address, and a duplicate registration deliberately sends **nothing**:
    a second email would confirm to whoever triggered it that the first account
    exists.
    """
    try:
        async with _unscoped_session() as db:
            user_id = await register_user(
                db,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name,
            )
            issued = await issue_verification(db, user_id=user_id, email=payload.email)
            await db.commit()
    except EmailAlreadyRegisteredError:
        log.info("auth.register.duplicate")
        return {"status": "check_your_email"}
    except WeakPasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    _send_later(
        background,
        build_mailer(settings),
        build_verification_email(
            to=payload.email, token=issued.token, base_url=settings.public_base_url
        ),
    )
    log.info("auth.register.verification_queued")
    return {"status": "check_your_email"}


# ── Password reset ────────────────────────────────────────────


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


@router.post("/password-reset/request")
async def request_password_reset(
    payload: PasswordResetRequest,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Send a reset link, if there is anywhere to send it.

    **The response is byte-identical either way**, and deliberately so: this is
    the cheapest endpoint in the product to query, it needs no account to reach,
    and a one-word difference between "sent" and "no such account" is a complete
    account-enumeration oracle.

    The two paths are kept as short and as similar as possible for that reason —
    `password_reset.request` returns `None` rather than raising, and the send is
    queued rather than awaited, so neither control flow nor the clock
    distinguishes them.
    """
    async with _unscoped_session() as db:
        issued = await password_reset.request(db, email=payload.email)
        await db.commit()

    if issued is not None:
        _send_later(
            background,
            build_mailer(settings),
            password_reset.build_email(
                to=issued.email, token=issued.token, base_url=settings.public_base_url
            ),
        )

    # No `email` field, no count, no timing tell. Logged without the address:
    # which addresses ask for resets is the fact this endpoint protects.
    log.info("auth.password_reset.requested")
    return {"status": "check_your_email"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(payload: PasswordResetConfirm) -> dict[str, str]:
    """Set a new password and sign the account out everywhere.

    One message for expired, already-used and never-existed, exactly as
    `/auth/verify-email` does. Telling them apart would confirm which tokens
    were real.
    """
    try:
        async with _unscoped_session() as db:
            user_id = await password_reset.confirm(
                db, token=payload.token, new_password=payload.password
            )
            await db.commit()
    except WeakPasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That link is invalid or has expired.")

    log.info("auth.password_reset.confirmed")
    return {"status": "password_updated"}


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


# `POST /auth/workspace` stood here until P3, with a `_teardown_on_switch` hook
# beside it holding the seam for doc 06 §2.1's agent teardown and cache
# invalidation on switch.
#
# Both are deleted rather than left in place, because `doc/11` §3.2 removed the
# thing they served: **a NEXUS account belongs to one company**, so there is
# never a second workspace to switch to. Keeping a validated, tested endpoint
# for a state the product no longer has would be keeping an attack surface for a
# feature nobody can reach — and keeping the teardown hook would be keeping a
# seam for an invariant (I5) that no longer applies.
#
# I5's cache-invalidation-on-switch requirement is void with it; scope-keyed
# caching remains, and remains necessary, for **role change**, which is still
# immediate (doc 06 §4.15). `ARCHITECTURE-HLD.md` §4.6 records that.
#
# `membership_own_rows` from migration 0003 stays. Login still reads it to find
# the one workspace, and `SessionResponse.workspaces` is still a list — the
# schema is many-to-many by choice (see `app/domain/membership.py`), so the
# shape that carries zero or one entry today can carry more if the agency case
# in doc 06 §2.1 is ever revived.


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
