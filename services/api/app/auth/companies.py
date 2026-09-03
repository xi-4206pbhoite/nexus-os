"""Creating a company — the authenticated product's entry point.

`doc/12` §Phase 5. Until now the only path that inserted a `workspace` was
`create_workspace_for_claim`, which required a verified domain first (doc 07 M3).
D19 split that: **creation needs no claim**, and verification gates inviting and
connecting instead. `app/auth/workspaces.py` argues why.

One transaction, three rows — `tenant`, `workspace`, owner `membership` — plus a
queued `research_run`. Atomic because a workspace with no members is unreachable
by everyone including the person who just made it, and there is no path in the
product to add the first one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.workspaces import find_verified_workspace_for_domain
from app.connectors.domain_check import normalise_domain
from app.domain import audit
from app.domain.membership import assert_no_live_membership
from app.logging import get_logger

log = get_logger(__name__)

# `doc/11` §5: 45 days, not 14. The trial has to outlast the onboarding it is
# meant to demonstrate, and onboarding depends on a customer gathering documents.
TRIAL = timedelta(days=45)


@dataclass(frozen=True, slots=True)
class CompanyDetails:
    """The five fields `doc/12` §Phase 5 asks for.

    `website_url` is **mandatory** (`doc/11` Q13). It is not decoration: it is
    the first fact NEXUS holds about the company and the input the research run
    is queued against. A company with no URL is a company the product cannot
    begin to learn.
    """

    name: str
    website_url: str
    country: str
    reporting_currency: str
    headcount_band: str


@dataclass(frozen=True, slots=True)
class CreatedCompany:
    workspace_id: UUID
    tenant_id: UUID
    domain: str
    research_run_id: UUID


class CompanyRegistrationError(Exception):
    """A refusal a person can act on."""


class DomainAlreadyRegisteredError(CompanyRegistrationError):
    """`doc/11` Q8 — the domain belongs to a workspace that has proved it.

    Carries the workspace id, because the caller's job is to offer a **join
    request** rather than a refusal. Two colleagues signing up separately is the
    ordinary case, not an attack, and answering it with a second workspace
    splits one company's data in half silently — the worst outcome available.
    """

    def __init__(self, workspace_id: UUID, domain: str) -> None:
        super().__init__(
            f"{domain} is already set up on NEXUS OS. Ask to join that company, "
            "or confirm that yours is a different business using the same domain."
        )
        self.workspace_id = workspace_id
        self.domain = domain


def domain_of(website_url: str) -> str:
    """The registrable domain from a URL the user typed.

    People type `acme.om`, not `https://acme.om`. Normalised through
    `domain_check.normalise_domain` — the same function domain *verification*
    uses — because the two must agree: a domain registered one way and verified
    another would never match, and the mismatch would look like a verification
    that simply never succeeds.
    """
    raw = website_url.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    host = urlparse(raw).hostname or ""
    return normalise_domain(host)


async def create_company(
    db: AsyncSession, *, user_id: UUID, details: CompanyDetails, allow_duplicate: bool = False
) -> CreatedCompany:
    """Create the company, its workspace, its owner and its first research run.

    `allow_duplicate` is how `doc/11` Q8's escape hatch is expressed: two
    genuinely different businesses can share a domain — an agency and its
    trading arm, a group with one website — so the second registration is
    *possible* and must be **explicitly confirmed** rather than silently
    permitted. Defaulting it to `True` would turn a deliberate branch into a
    thing nobody sees.
    """
    await assert_no_live_membership(db, user_id=user_id)

    domain = domain_of(details.website_url)

    if not allow_duplicate:
        # Through `nexus_jobs`, not this session. `workspace` is row-level
        # secured, so the application role sees only workspaces the caller
        # belongs to — and someone registering a *new* company belongs to none.
        # Asking here would return nothing every time, which is finding #18 and
        # is exactly the bug this branch was written to avoid inheriting.
        holder = await find_verified_workspace_for_domain(domain)
        if holder is not None:
            raise DomainAlreadyRegisteredError(holder, domain)

    tenant_id = UUID(
        str(
            (
                await db.execute(
                    text("INSERT INTO tenant (name) VALUES (:n) RETURNING id"),
                    {"n": details.name},
                )
            ).scalar_one()
        )
    )

    # Minted here, and the GUC set *before* the insert. `workspace` carries
    # FORCE ROW LEVEL SECURITY and its WITH CHECK compares the new row's
    # `workspace_id` against `nexus.workspace_id`; with the GUC unset that
    # comparison is NULL and Postgres refuses the row.
    #
    # This is the M4 defect, and it is worth repeating rather than referring to:
    # the previous version let the database generate both values, which made
    # `workspace_id` a different uuid from `id`, so every call failed and no
    # workspace could be created through the API at all.
    workspace_id = uuid4()
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )

    await db.execute(
        text(
            "INSERT INTO workspace"
            " (id, workspace_id, tenant_id, name, domain, country,"
            "  reporting_currency, headcount_band, website_url, trial_ends_at)"
            " VALUES (:id, :id, :t, :n, :d, :c, :cur, :hb, :url, :trial)"
        ),
        {
            "id": str(workspace_id),
            "t": str(tenant_id),
            "n": details.name,
            "d": domain,
            "c": details.country,
            "cur": details.reporting_currency,
            "hb": details.headcount_band,
            "url": details.website_url.strip(),
            "trial": datetime.now(UTC) + TRIAL,
        },
    )

    await db.execute(
        text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w, :u, 'owner', ARRAY['executive']::text[])"
        ),
        {"w": str(workspace_id), "u": str(user_id)},
    )

    # Enqueued, not fired. P11 builds the engine; recording the request means it
    # survives a restart, and the queue is inspectable before anything drains it.
    research_run_id = UUID(
        str(
            (
                await db.execute(
                    text(
                        "INSERT INTO research_run (workspace_id, requested_by_user_id)"
                        " VALUES (:w, :u) RETURNING id"
                    ),
                    {"w": str(workspace_id), "u": str(user_id)},
                )
            ).scalar_one()
        )
    )

    await audit.record(
        db,
        workspace_id=workspace_id,
        action=audit.AuditAction.WORKSPACE_CREATED,
        actor_user_id=user_id,
        target_type="workspace",
        target_id=str(workspace_id),
        reason=f"registered {domain}, unverified",
    )

    log.info("company.created", domain=domain, duplicate_allowed=allow_duplicate)
    return CreatedCompany(
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        domain=domain,
        research_run_id=research_run_id,
    )
