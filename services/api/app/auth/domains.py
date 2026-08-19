"""Domain claims, and what verification is now for.

**The old invariant was "no workspace exists without a verified domain".
ADR 0013 replaced it**, because it left registration with nowhere to go: a new
account signed in and then had no workspace, so every workspace-scoped screen
answered 403. Two creation paths now exist and the difference between them is the
whole point:

- `create_workspace_at_registration` — no verification. The domain is *inferred*
  from the sign-up email and stored with `domain_verified_at IS NULL`. A label,
  never an authorisation input.
- `create_workspace_for_claim` — unchanged. Still the only path to a **verified**
  domain, and still the only thing the partial unique index constrains.

So verification stopped being a gate and became a claim to authority. What it buys
is exclusivity: first verified wins (doc 06 §1.1), enforced by the partial unique
index on `lower(domain) WHERE domain_verified_at IS NOT NULL` from migration 0002,
so a race between two claimants is resolved by Postgres rather than by application
timing. The loser enters a dispute rather than silently failing or, worse, silently
succeeding into a second *verified* workspace for the same company.

What it no longer buys is preventing an unverified workspace from carrying the same
domain string. That is the cost, and `create_workspace_at_registration` documents
what bounds it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.domain_check import (
    STRENGTH_BY_METHOD,
    CheckResult,
    Method,
    Strength,
    check_dns_txt,
    check_well_known_file,
    email_domain_matches,
    is_free_email_domain,
    new_challenge,
    normalise_domain,
)
from app.logging import get_logger

log = get_logger(__name__)

CLAIM_TTL = timedelta(days=14)
# Doc 06 §1.1 requires re-verification on a cadence. Monthly is frequent enough
# to catch a lapsed domain without hammering DNS.
RECHECK_INTERVAL = timedelta(days=30)


class DomainClaimError(Exception):
    """A claim cannot proceed. The message is safe to show the claimant."""


class DomainDisputedError(DomainClaimError):
    """Another workspace already holds this domain."""


@dataclass(frozen=True, slots=True)
class Claim:
    id: UUID
    domain: str
    user_id: UUID
    method: Method
    strength: Strength
    challenge_token: str
    state: str
    evidence: str | None
    verified_at: datetime | None


# ── Starting a claim ──────────────────────────────────────────


async def start_claim(db: AsyncSession, *, user_id: UUID, raw_domain: str, method: Method) -> Claim:
    domain = normalise_domain(raw_domain)
    if not domain or "." not in domain:
        raise DomainClaimError("Enter a valid domain, for example acme.om")

    # Replace any previous live attempt rather than accumulating tokens that
    # all remain valid.
    await db.execute(
        text(
            "UPDATE domain_claim SET state = 'expired'"
            " WHERE lower(domain) = :d AND user_id = :u AND state = 'pending'"
        ),
        {"d": domain, "u": str(user_id)},
    )

    strength = STRENGTH_BY_METHOD[method]
    challenge = new_challenge()
    expires_at = datetime.now(UTC) + CLAIM_TTL

    row = await db.execute(
        text(
            "INSERT INTO domain_claim"
            " (domain, user_id, method, strength, challenge_token, state, expires_at)"
            " VALUES (:d, :u, :m, :s, :c, 'pending', :e) RETURNING id"
        ),
        {
            "d": domain,
            "u": str(user_id),
            "m": method.value,
            "s": strength.value,
            "c": challenge,
            "e": expires_at,
        },
    )
    return Claim(
        id=UUID(str(row.scalar_one())),
        domain=domain,
        user_id=user_id,
        method=method,
        strength=strength,
        challenge_token=challenge,
        state="pending",
        evidence=None,
        verified_at=None,
    )


async def _load_claim(db: AsyncSession, claim_id: UUID, user_id: UUID) -> Claim:
    row = (
        await db.execute(
            text(
                "SELECT id, domain, user_id, method, strength, challenge_token,"
                "       state, evidence, verified_at, expires_at"
                "  FROM domain_claim WHERE id = :id AND user_id = :u"
            ),
            {"id": str(claim_id), "u": str(user_id)},
        )
    ).first()

    # Same response whether the claim belongs to someone else or does not
    # exist: confirming it exists is a disclosure.
    if row is None:
        raise DomainClaimError("No such claim.")

    if row.expires_at <= datetime.now(UTC) and row.state == "pending":
        raise DomainClaimError("This verification has expired. Start a new one.")

    return Claim(
        id=UUID(str(row.id)),
        domain=row.domain,
        user_id=UUID(str(row.user_id)),
        method=Method(row.method),
        strength=Strength(row.strength),
        challenge_token=row.challenge_token,
        state=row.state,
        evidence=row.evidence,
        verified_at=row.verified_at,
    )


# ── Checking a claim ──────────────────────────────────────────


async def check_claim(
    db: AsyncSession, *, claim_id: UUID, user_id: UUID, user_email: str | None = None
) -> Claim:
    """Run the claim's method and record the outcome."""
    claim = await _load_claim(db, claim_id, user_id)
    if claim.state == "verified":
        return claim

    if claim.method is Method.DNS_TXT:
        result = await check_dns_txt(claim.domain, claim.challenge_token)
    elif claim.method is Method.FILE:
        result = await check_well_known_file(claim.domain, claim.challenge_token)
    elif claim.method is Method.EMAIL:
        # Weak: the address proves employment, not authority. It is only
        # accepted once the address itself has been verified, or anyone could
        # claim any domain by typing an address at it.
        if not user_email:
            raise DomainClaimError("Verify your email address first.")
        matched = email_domain_matches(user_email, claim.domain)
        result = CheckResult(
            verified=matched,
            evidence=(
                f"Email address is on {claim.domain}"
                if matched
                else "Your email address is not on this domain."
            ),
        )
    else:
        raise DomainClaimError("This verification method requires support review.")

    now = datetime.now(UTC)
    if result.verified:
        await db.execute(
            text(
                "UPDATE domain_claim"
                "   SET state = 'verified', verified_at = :now, last_checked_at = :now,"
                "       next_check_at = :next, evidence = :ev"
                " WHERE id = :id"
            ),
            {
                "now": now,
                "next": now + RECHECK_INTERVAL,
                "ev": result.evidence,
                "id": str(claim.id),
            },
        )
        log.info("domain.verified", method=claim.method.value, strength=claim.strength.value)
    else:
        # Deliberately left pending, not failed: the claimant is expected to
        # publish the record and try again.
        await db.execute(
            text("UPDATE domain_claim SET last_checked_at = :now, evidence = :ev WHERE id = :id"),
            {"now": now, "ev": result.evidence, "id": str(claim.id)},
        )

    return await _load_claim(db, claim_id, user_id)


# ── The gate ──────────────────────────────────────────────────


async def create_workspace_at_registration(
    db: AsyncSession, *, user_id: UUID, email: str, workspace_name: str | None = None
) -> UUID:
    """Create a workspace for a brand-new account, with **no domain verification**.

    **ADR 0013 supersedes doc 07 M3's invariant** — *"no workspace exists without a
    verified domain"* — because that invariant left registration with nowhere to go:
    a new account signed in successfully and then had no workspace, so every
    workspace-scoped screen answered 403. `create_workspace_for_claim` stays exactly
    as it was and remains correct for the verified route; this is a second door, not
    a weakening of that one.

    No migration was needed, which is worth stating because it is evidence rather
    than convenience: `workspace.domain` and `domain_verified_at` are both nullable,
    and the unique index on domain is *partial* — it constrains only rows where
    `domain_verified_at IS NOT NULL`. `test_the_uniqueness_only_applies_to_verified_domains`
    has always asserted that. The schema anticipated an unverified workspace; only
    the application refused to make one.

    **What this gives up.** Two workspaces can now hold the same domain string, as
    long as at most one of them is verified. So a stranger registering
    `someone@acme.om` gets a workspace claiming `acme.om` that nobody checked. Three
    things bound the damage, and none of them makes it disappear:

    - Row-level security is per workspace, not per domain, so the two see nothing of
      each other. The domain string is a label here, never an authorisation input.
    - `owner_claim_review` is set, because an inferred domain is precisely an
      unreviewed owner claim. It is the artefact a support conversation needs.
    - Verification remains available and is what still decides the unique index, so
      the real owner can always take the verified slot.

    The domain is inferred from the email, since the sign-up form asks for a work
    address. A free provider yields **no** domain rather than a wrong one: a
    workspace called `gmail.com` claiming `gmail.com` would be a workspace for
    Gmail, which is the same reasoning `begin_domain_claim` already applies.
    """
    domain = normalise_domain(email)
    inferred = bool(domain) and not is_free_email_domain(domain)

    name = (workspace_name or "").strip() or (domain if inferred else email.split("@")[0])

    # Minted here and the GUC set before the INSERT, for the reason spelled out in
    # `create_workspace_for_claim`: `workspace` carries FORCE ROW LEVEL SECURITY and
    # its WITH CHECK compares the new row's `workspace_id` against the GUC, so
    # letting the database generate them is refused outright.
    workspace_id = uuid4()
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :ws, true)"),
        {"ws": str(workspace_id)},
    )

    # Tenant, workspace and membership in **one statement**, not three.
    #
    # This is on the registration path, and every statement here is a round trip to
    # a managed database that may be an ocean away — measured at roughly 600ms
    # each from a development laptop, which made registration an 8-11 second
    # request and pushed it past the web proxy's 15s timeout. Three inserts became
    # one, and the ordering the CTEs express is the same ordering the foreign keys
    # require, so nothing is lost by collapsing them.
    #
    # The GUC still has to be its own statement: `set_config(..., is_local => true)`
    # must be committed to the transaction's state before the row that RLS will
    # check against it is written.
    await db.execute(
        text(
            "WITH t AS ("
            "  INSERT INTO tenant (name) VALUES (:n) RETURNING id"
            "), w AS ("
            "  INSERT INTO workspace"
            "    (id, workspace_id, tenant_id, name, domain, domain_verified_at,"
            "     verification_method, owner_claim_review, trial_ends_at)"
            "  SELECT :id, :id, t.id, :n, :d, NULL, NULL, true, :trial FROM t"
            "  RETURNING id"
            ")"
            " INSERT INTO membership (workspace_id, user_id, role, departments)"
            " SELECT w.id, :u, 'owner', ARRAY['executive']::text[] FROM w"
        ),
        {
            "id": str(workspace_id),
            "n": name,
            # NULL rather than a free-provider host. A wrong domain is worse than
            # none: the crawler and the Brain would both treat it as the company.
            "d": domain if inferred else None,
            "trial": datetime.now(UTC) + timedelta(days=14),
            # Owner, and never scoped to one department (doc 06 §2.2).
            "u": str(user_id),
        },
    )

    log.info("workspace.created_at_registration", domain_inferred=inferred, verified=False)
    return workspace_id


async def create_workspace_for_claim(
    db: AsyncSession, *, claim_id: UUID, user_id: UUID, workspace_name: str
) -> UUID:
    """The only path that creates a **verified** workspace.

    Every precondition is checked here rather than at the route, so there is one
    place to attack and one place to audit.

    It is no longer the only path that creates a workspace at all — see
    `create_workspace_at_registration` and ADR 0013. Nothing in this function
    changed: verification still decides the partial unique index, so this remains
    the only way to hold a domain *authoritatively*.
    """
    claim = await _load_claim(db, claim_id, user_id)

    if claim.state == "disputed":
        raise DomainDisputedError("This domain is already claimed by another workspace.")
    if claim.state != "verified" or claim.verified_at is None:
        raise DomainClaimError("Verify the domain before creating a workspace.")

    existing = (
        await db.execute(
            text(
                "SELECT id FROM workspace"
                " WHERE lower(domain) = :d AND domain_verified_at IS NOT NULL"
            ),
            {"d": claim.domain},
        )
    ).first()

    if existing is not None:
        # First verified wins. The loser gets a dispute record rather than a
        # silent failure — someone has to be able to resolve this, and a
        # support conversation needs an artefact.
        await db.execute(
            text(
                "UPDATE domain_claim SET state = 'disputed', disputes_workspace_id = :ws"
                " WHERE id = :id"
            ),
            {"ws": str(existing.id), "id": str(claim.id)},
        )
        raise DomainDisputedError("This domain is already claimed by another workspace.")

    tenant_row = await db.execute(
        text("INSERT INTO tenant (name) VALUES (:n) RETURNING id"),
        {"n": workspace_name},
    )
    tenant_id = UUID(str(tenant_row.scalar_one()))

    # The id is minted here rather than by the database, because the GUC has to
    # be set *before* the INSERT and the INSERT is what would otherwise reveal
    # the id. `workspace` carries FORCE ROW LEVEL SECURITY like every other
    # workspace-scoped table, and its WITH CHECK compares the new row's
    # `workspace_id` against `nexus.workspace_id`; with the GUC unset that
    # comparison is NULL and Postgres refuses the row.
    #
    # This was a real failure, not a hypothetical one: the previous version let
    # the database generate both values, which made `workspace_id` a *different*
    # random uuid from `id` and set the GUC afterwards. Every call raised
    # `new row violates row-level security policy for table "workspace"`, so no
    # workspace could be created through the API at all. It survived because M3's
    # tests insert workspaces directly — with `id` and `workspace_id` equal and
    # the GUC already set, which is what the migration's comment intends by
    # "`workspace_id` mirrors `id`" and what this now does.
    workspace_id = uuid4()
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :ws, true)"),
        {"ws": str(workspace_id)},
    )

    try:
        await db.execute(
            text(
                "INSERT INTO workspace"
                " (id, workspace_id, tenant_id, name, domain, domain_verified_at,"
                "  verification_method, owner_claim_review, trial_ends_at)"
                " VALUES (:id, :id, :t, :n, :d, :v, :m, :review, :trial)"
            ),
            {
                "id": str(workspace_id),
                "t": str(tenant_id),
                "n": workspace_name,
                "d": claim.domain,
                "v": claim.verified_at,
                "m": claim.method.value,
                # A weak claim proves employment, not authority — flag it so a
                # second person from the same domain triggers review.
                "review": claim.strength is Strength.WEAK,
                "trial": datetime.now(UTC) + timedelta(days=14),
            },
        )
    except IntegrityError as exc:
        # Lost the race between the SELECT above and this INSERT. The partial
        # unique index is what actually decides, which is the point of having
        # it — application timing does not.
        await db.rollback()
        raise DomainDisputedError(
            "This domain was claimed by another workspace moments ago."
        ) from exc

    # The creator is Owner and cannot be scoped to one department (doc 06 §2.2).
    await db.execute(
        text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:ws, :u, 'owner', ARRAY['executive']::text[])"
        ),
        {"ws": str(workspace_id), "u": str(user_id)},
    )
    await db.execute(
        text("UPDATE domain_claim SET workspace_id = :ws WHERE id = :id"),
        {"ws": str(workspace_id), "id": str(claim.id)},
    )

    log.info("workspace.created", method=claim.method.value, strength=claim.strength.value)
    return workspace_id


# ── Revocation and re-verification ────────────────────────────


async def revoke_claim(db: AsyncSession, *, claim_id: UUID, reason: str) -> None:
    """Used when the verifying method stops resolving (doc 06 §1.1).

    The workspace is *not* deleted — that would destroy a customer's data on a
    DNS blip. It is marked for review instead.
    """
    await db.execute(
        text(
            "UPDATE domain_claim"
            "   SET state = 'revoked', revoked_at = now(), revoked_reason = :r"
            " WHERE id = :id"
        ),
        {"r": reason, "id": str(claim_id)},
    )
    await db.execute(
        text(
            "UPDATE workspace SET owner_claim_review = true"
            " WHERE id = (SELECT workspace_id FROM domain_claim WHERE id = :id)"
        ),
        {"id": str(claim_id)},
    )
    log.info("domain.revoked", reason=reason)


async def claims_due_for_recheck(db: AsyncSession, *, limit: int = 100) -> list[UUID]:
    rows = (
        await db.execute(
            text(
                "SELECT id FROM domain_claim"
                " WHERE state = 'verified' AND next_check_at IS NOT NULL"
                "   AND next_check_at <= now() AND revoked_at IS NULL"
                " ORDER BY next_check_at LIMIT :lim"
            ),
            {"lim": limit},
        )
    ).all()
    return [UUID(str(r.id)) for r in rows]
