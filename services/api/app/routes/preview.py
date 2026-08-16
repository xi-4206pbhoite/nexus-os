"""The unauthenticated Preview audit.

Doc 06 §1.1: before domain verification the workspace is ephemeral and the audit
is **reduced** — brand, performance and technical SEO on the entered domain
only. No competitor discovery, no keyword data, no downloadable output, nothing
persisted to a Brain, and a short TTL.

The reason is not caution about cost. Anyone can type a competitor's URL, and
without that limit NEXUS would crawl a company the requester does not own, name
its competitors, and hand that to a stranger — a competitive-intelligence
product sold by accident.

This is the only unauthenticated endpoint that performs a server-side fetch, so
every guard in `connectors/` converges here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.calculators.audit import LOCKED_IN_PREVIEW, build_preview_audit
from app.config import Settings, get_settings
from app.connectors.crawler import FetchError, fetch_page
from app.connectors.extract import extract_signals
from app.connectors.rate_limit import (
    GLOBAL_DAILY,
    PER_DOMAIN,
    PER_IP,
    RateLimitedError,
    check_and_increment,
    hash_ip,
)
from app.connectors.ssrf import UrlNotAllowedError, validate_url
from app.db import _unscoped_session
from app.logging import get_logger

router = APIRouter(prefix="/preview", tags=["preview"])
log = get_logger(__name__)


class PreviewRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2048)


class CheckOut(BaseModel):
    id: str
    label: str
    passed: bool
    evidence: str


class CategoryOut(BaseModel):
    category: str
    score: int
    max_score: int
    percentage: int
    checks: list[CheckOut]


class LockedOut(BaseModel):
    category: str
    unlock: str


class PreviewOut(BaseModel):
    preview_id: UUID
    domain: str
    final_url: str
    overall: int
    scored_categories: int
    categories: list[CategoryOut]
    locked: list[LockedOut]
    expires_at: datetime
    truncated: bool = False


def client_ip(request: Request, settings: Settings) -> str:
    """The address to rate-limit against.

    `X-Forwarded-For` is attacker-controlled by default — anyone can send it,
    and believing it lets one client mint unlimited rate-limit identities.
    It is therefore honoured **only** when the direct peer is a configured
    trusted proxy.

    The trade-off is real in both directions: with no trusted proxy configured,
    every visitor arriving through one shares a single bucket, and the per-IP
    limit collapses into a global one. That is the safe failure, but it is a
    failure — so any deployment behind a proxy must set `NEXUS_TRUSTED_PROXY_IPS`.
    """
    peer = request.client.host if request.client else "unknown"
    if peer not in settings.trusted_proxies:
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    # Left-most entry is the original client; the rest are hops.
    original = forwarded.split(",")[0].strip()
    return original or peer


@router.post("", response_model=PreviewOut, status_code=status.HTTP_201_CREATED)
async def create_preview(
    payload: PreviewRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PreviewOut:
    raw = payload.url.strip()
    if "://" not in raw:
        # People type "acme.om", not "https://acme.om".
        raw = f"https://{raw}"

    # Validate before spending any budget: a blocked URL must not consume a
    # rate-limit slot, or the guard becomes a way to exhaust someone's quota.
    try:
        target = validate_url(raw)
    except UrlNotAllowedError as exc:
        log.info("preview.blocked", reason=str(exc))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That address cannot be analysed."
        ) from exc

    domain = target.host.lower()
    ip_key = hash_ip(
        client_ip(request, settings), secret=settings.require("storage_signing_secret")
    )

    async with _unscoped_session() as db:
        try:
            # Global ceiling first: it is the one that protects the bill, and
            # checking it last would let a burst past it while per-key limits
            # were still being evaluated.
            await check_and_increment(db, GLOBAL_DAILY, "preview")
            await check_and_increment(db, PER_IP, ip_key)
            await check_and_increment(db, PER_DOMAIN, domain)
        except RateLimitedError as exc:
            await db.commit()  # keep the increments; the attempt still counts
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many analyses right now. Please try again later.",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc
        await db.commit()

    try:
        page = await fetch_page(
            raw,
            max_bytes=settings.crawl_max_bytes,
            timeout_seconds=settings.crawl_timeout_seconds,
            max_redirects=settings.crawl_max_redirects,
        )
    except FetchError as exc:
        await _record_failure(domain, raw, exc.reason, blocked=exc.blocked, settings=settings)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.reason) from exc

    signals = extract_signals(page.html, url=page.final_url)
    audit = build_preview_audit(signals)
    expires_at = datetime.now(UTC) + timedelta(days=settings.preview_ttl_days)

    categories = [
        CategoryOut(
            category=c.category,
            score=c.score,
            max_score=c.max_score,
            percentage=c.percentage,
            checks=[
                CheckOut(id=k.id, label=k.label, passed=k.passed, evidence=k.evidence)
                for k in c.checks
            ],
        )
        for c in audit.categories
    ]

    async with _unscoped_session() as db:
        row = await db.execute(
            text(
                "INSERT INTO preview_session"
                " (domain, requested_url, status, audit_json, requester_ip_hash, expires_at)"
                " VALUES (:d, :u, 'complete', :a, :ip, :exp) RETURNING id"
            ),
            {
                "d": domain,
                "u": raw,
                "a": PreviewOut(
                    preview_id=UUID(int=0),
                    domain=domain,
                    final_url=page.final_url,
                    overall=audit.overall,
                    scored_categories=audit.scored_count,
                    categories=categories,
                    locked=[],
                    expires_at=expires_at,
                ).model_dump_json(),
                "ip": ip_key,
                "exp": expires_at,
            },
        )
        preview_id = UUID(str(row.scalar_one()))
        await db.commit()

    log.info("preview.complete", domain=domain, overall=audit.overall)

    return PreviewOut(
        preview_id=preview_id,
        domain=domain,
        final_url=page.final_url,
        overall=audit.overall,
        scored_categories=audit.scored_count,
        categories=categories,
        locked=[
            LockedOut(category=name, unlock=unlock) for name, unlock in LOCKED_IN_PREVIEW.items()
        ],
        expires_at=expires_at,
        truncated=page.truncated,
    )


async def _record_failure(
    domain: str, url: str, reason: str, *, blocked: bool, settings: Settings
) -> None:
    expires_at = datetime.now(UTC) + timedelta(days=settings.preview_ttl_days)
    async with _unscoped_session() as db:
        await db.execute(
            text(
                "INSERT INTO preview_session"
                " (domain, requested_url, status, error_reason, expires_at)"
                " VALUES (:d, :u, :s, :r, :exp)"
            ),
            {
                "d": domain,
                "u": url,
                "s": "blocked" if blocked else "failed",
                "r": reason,
                "exp": expires_at,
            },
        )
        await db.commit()
