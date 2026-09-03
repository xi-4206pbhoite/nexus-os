"""Email verification, domain claims, and workspace creation.

The endpoints behind doc 07 M3. Note what is *not* here: there is no
`POST /workspaces` that takes a domain. The only way a workspace comes into
existence is `POST /domains/{claim_id}/workspace`, which requires a verified
claim owned by the caller — so the gate cannot be walked around by finding a
different route.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth.csrf import require_csrf
from app.auth.domains import (
    DomainClaimError,
    DomainDisputedError,
    create_workspace_for_claim,
    load_claim_for_check,
    perform_check,
    record_check_result,
    start_claim,
)
from app.auth.email_verification import consume
from app.auth.service import resolve_session
from app.config import Settings, get_settings
from app.connectors.domain_check import (
    WELL_KNOWN_PATH,
    Method,
    expected_txt_value,
    is_free_email_domain,
    normalise_domain,
)

# Aliased: `consume` already means "spend a verification token" in this module,
# and two functions with one name in one file is how the wrong one gets called.
from app.connectors.rate_limit import CHECK_PER_DOMAIN, CHECK_PER_USER
from app.connectors.rate_limit import consume as meter
from app.db import _unscoped_session
from app.domain.membership import UserAlreadyInAWorkspaceError
from app.logging import get_logger

router = APIRouter(tags=["onboarding"])
log = get_logger(__name__)


# ── Email verification ────────────────────────────────────────


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)


@router.post("/auth/verify-email")
async def verify_email(payload: VerifyEmailRequest) -> dict[str, str]:
    async with _unscoped_session() as db:
        user_id = await consume(db, token=payload.token)
        await db.commit()

    if user_id is None:
        # One message for expired, already-used and never-existed. Telling them
        # apart would confirm which tokens were real.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That link is invalid or has expired.")

    return {"status": "verified"}


# ── Domain claims ─────────────────────────────────────────────


class StartClaimRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    method: Method


class ClaimOut(BaseModel):
    claim_id: UUID
    domain: str
    method: Method
    strength: str
    state: str
    instruction: str
    evidence: str | None = None


def _instruction(method: Method, domain: str, challenge: str) -> str:
    if method is Method.DNS_TXT:
        return (
            f"Add a TXT record to {domain} with the value:\n"
            f"{expected_txt_value(challenge)}\n"
            "DNS changes can take a few minutes to propagate."
        )
    if method is Method.FILE:
        return (
            f"Publish a file at https://{domain}{WELL_KNOWN_PATH} containing exactly:\n{challenge}"
        )
    if method is Method.EMAIL:
        return (
            f"Confirm the email address on your account is at {domain}. "
            "This is a weaker check than DNS or a file, so the workspace will "
            "be flagged for review if someone else from your company registers."
        )
    return "Contact support with documentary evidence of ownership."


async def _require_user(nexus_session: str | None) -> UUID:
    if not nexus_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    async with _unscoped_session() as db:
        resolved = await resolve_session(db, token=nexus_session)
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return resolved.user_id


@router.post("/domains", response_model=ClaimOut, dependencies=[Depends(require_csrf)])
async def begin_domain_claim(
    payload: StartClaimRequest,
    nexus_session: Annotated[str | None, Cookie(alias="nexus_session")] = None,
) -> ClaimOut:
    user_id = await _require_user(nexus_session)
    domain = normalise_domain(payload.domain)

    if payload.method is Method.EMAIL and is_free_email_domain(domain):
        # A gmail.com workspace would be a workspace for Gmail.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That is a personal email provider, not a company domain.",
        )

    try:
        async with _unscoped_session() as db:
            claim = await start_claim(
                db, user_id=user_id, raw_domain=payload.domain, method=payload.method
            )
            await db.commit()
    except DomainClaimError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return ClaimOut(
        claim_id=claim.id,
        domain=claim.domain,
        method=claim.method,
        strength=claim.strength.value,
        state=claim.state,
        instruction=_instruction(claim.method, claim.domain, claim.challenge_token),
    )


@router.post(
    "/domains/{claim_id}/check", response_model=ClaimOut, dependencies=[Depends(require_csrf)]
)
async def check_domain_claim(
    claim_id: UUID,
    nexus_session: Annotated[str | None, Cookie(alias="nexus_session")] = None,
) -> ClaimOut:
    user_id = await _require_user(nexus_session)

    # Finding #11. Three steps, and the middle one holds no session.
    #
    # This was one `async with` around a load, a DNS or HTTP call against a host
    # the claimant named, and a write. A slow or deliberately tarpitting target
    # therefore held a pooled connection for its whole timeout — ten concurrent
    # checks exhausted a pool of five and every other request in the process
    # queued behind them. The caller chooses the target, so the trigger is not
    # bad luck.
    async with _unscoped_session() as db:
        email = (
            await db.execute(
                text("SELECT email FROM app_user WHERE id = :u AND email_verified_at IS NOT NULL"),
                {"u": str(user_id)},
            )
        ).scalar()
        loaded = await load_claim_for_check(db, claim_id=claim_id, user_id=user_id)

    if loaded.state == "verified":
        claim = loaded
    else:
        # Finding #4. Metered before the fetch, not after: the point is to stop
        # the outbound request being made, and a limit checked afterwards has
        # already sent it.
        #
        # A 429 is safe here where it was not on `/auth/login` — the caller has
        # already proved they own this claim, so refusing them discloses nothing
        # about anyone else. The *scope* is still withheld: which bucket ran out
        # is our business, and saying "this domain has been checked too often"
        # would tell one claimant about another's activity.
        async with _unscoped_session() as db:
            over_user = await meter(db, CHECK_PER_USER, str(user_id))
            over_domain = await meter(db, CHECK_PER_DOMAIN, loaded.domain)
            await db.commit()

        if over_user or over_domain:
            log.info("domain.check.rate_limited")
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "That domain has been checked too many times recently. "
                "DNS changes can take a few minutes to appear — try again shortly.",
                headers={"Retry-After": "300"},
            )

        # No session in scope here. Deliberately outside the block above rather
        # than merely after a commit: a commit ends the transaction and keeps
        # the connection, which is the resource that runs out.
        try:
            result = await perform_check(loaded, user_email=email)
        except DomainClaimError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

        async with _unscoped_session() as db:
            claim = await record_check_result(db, claim_id=claim_id, user_id=user_id, result=result)
            await db.commit()

    return ClaimOut(
        claim_id=claim.id,
        domain=claim.domain,
        method=claim.method,
        strength=claim.strength.value,
        state=claim.state,
        instruction=_instruction(claim.method, claim.domain, claim.challenge_token),
        evidence=claim.evidence,
    )


# ── Workspace creation ────────────────────────────────────────


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceOut(BaseModel):
    workspace_id: UUID
    name: str


@router.post(
    "/domains/{claim_id}/workspace",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_workspace(
    claim_id: UUID,
    payload: CreateWorkspaceRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    nexus_session: Annotated[str | None, Cookie(alias="nexus_session")] = None,
) -> WorkspaceOut:
    """The only path that creates a workspace.

    Every precondition lives in `create_workspace_for_claim`, not here, so
    there is one place to audit rather than one per route.
    """
    user_id = await _require_user(nexus_session)

    async with _unscoped_session() as db:
        try:
            workspace_id = await create_workspace_for_claim(
                db, claim_id=claim_id, user_id=user_id, workspace_name=payload.name
            )
        except UserAlreadyInAWorkspaceError as exc:
            # 409, and the message is the explanation rather than a status
            # name. `doc/11` §3.2 is a product rule a user has no way to infer,
            # so a bare "conflict" leaves them retrying the same button.
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except DomainDisputedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except DomainClaimError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

        await db.commit()

    return WorkspaceOut(workspace_id=workspace_id, name=payload.name)
