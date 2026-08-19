"""The unverified workspace registration creates (ADR 0013).

Against a **real** database, deliberately. The hermetic suite in
`test_registration_session.py` proves the route calls this; it cannot prove
Postgres accepts the row, and on this particular INSERT that gap has already cost
this project once. `create_workspace_for_claim` let the database generate `id` and
`workspace_id` — which made them different uuids — and set the RLS GUC afterwards,
so *every* call was refused with `new row violates row-level security policy for
table "workspace"` while the whole suite stayed green, because the tests inserted
workspaces themselves with the GUC already set.

So this suite drives the production function and lets Postgres judge it.

What it pins down:

- the row is written at all, with `id = workspace_id` and the GUC set first;
- `domain_verified_at IS NULL` — the workspace exists, the claim does not;
- a free email provider yields **no** domain rather than a wrong one;
- two *unverified* workspaces may share a domain, which is the cost ADR 0013
  accepts, asserted rather than left as prose;
- a verified workspace still excludes a second verified one, which is the half of
  M3 that survived (proved in `test_workspace_gate.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth.domains import create_workspace_at_registration
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.skipif(
    ASYNC_DB_URL is None,
    reason="No NEXUS_DATABASE_URL — the workspace INSERT is what needs a real database",
)

pytestmark = requires_db


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is always rolled back."""
    if ASYNC_DB_URL is None:
        pytest.skip("no database")

    engine = create_async_engine(ASYNC_DB_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


async def a_user(db: AsyncSession) -> UUID:
    user_id = uuid4()
    await db.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i, :e)"),
        {"i": str(user_id), "e": f"reg-{user_id}@example.test"},
    )
    return user_id


async def workspace_row(db: AsyncSession, workspace_id: UUID) -> object:
    """Read the row back, with the GUC set as the application would.

    Without the GUC the SELECT returns nothing — row-level security applies to us
    too — and a test that read `None` and asserted `is None` would pass for the
    wrong reason.
    """
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )
    return (
        await db.execute(
            text(
                "SELECT id, workspace_id, name, domain, domain_verified_at,"
                "       verification_method, owner_claim_review,"
                "       trial_ends_at IS NOT NULL AS has_trial"
                "  FROM workspace WHERE id = :i"
            ),
            {"i": str(workspace_id)},
        )
    ).one()


# ── The row reaches Postgres ───────────────────────────────────


async def test_a_workspace_is_created_without_any_verification(db: AsyncSession) -> None:
    """The whole point of ADR 0013, and the INSERT the hermetic suite cannot judge."""
    user_id = await a_user(db)

    workspace_id = await create_workspace_at_registration(
        db, user_id=user_id, email="founder@acmetrading.om"
    )
    row = await workspace_row(db, workspace_id)

    assert row.domain_verified_at is None, "the workspace exists; the claim does not"
    assert row.verification_method is None
    assert row.domain == "acmetrading.om"
    assert row.has_trial is True


async def test_workspace_id_mirrors_id(db: AsyncSession) -> None:
    """What migration 0002's comment means, and what the RLS `WITH CHECK` compares.

    Letting the database generate both is what broke `create_workspace_for_claim`:
    they came out as different uuids and every insert was refused.
    """
    user_id = await a_user(db)

    workspace_id = await create_workspace_at_registration(
        db, user_id=user_id, email="founder@acmetrading.om"
    )
    row = await workspace_row(db, workspace_id)

    assert row.id == row.workspace_id == workspace_id


async def test_the_creator_is_an_owner_in_the_executive_department(db: AsyncSession) -> None:
    """Doc 06 §2.2 — the creator cannot be scoped to a single department."""
    user_id = await a_user(db)

    workspace_id = await create_workspace_at_registration(
        db, user_id=user_id, email="founder@acmetrading.om"
    )
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )
    row = (
        await db.execute(
            text("SELECT role, departments FROM membership WHERE workspace_id = :w"),
            {"w": str(workspace_id)},
        )
    ).one()

    assert row.role == "owner"
    assert list(row.departments) == ["executive"]


async def test_an_unverified_workspace_is_flagged_for_review(db: AsyncSession) -> None:
    """An inferred domain is precisely an unreviewed owner claim.

    Nothing gates on the flag yet, so this is the artefact a support conversation
    will need rather than a control — recorded honestly as that.
    """
    user_id = await a_user(db)

    workspace_id = await create_workspace_at_registration(
        db, user_id=user_id, email="founder@acmetrading.om"
    )
    row = await workspace_row(db, workspace_id)

    assert row.owner_claim_review is True


# ── A wrong domain is worse than none ──────────────────────────


@pytest.mark.parametrize("provider", ["gmail.com", "hotmail.com", "yahoo.com"])
async def test_a_free_provider_yields_no_domain(db: AsyncSession, provider: str) -> None:
    """A workspace claiming `gmail.com` would be a workspace for Gmail.

    Worse, `domain` is what the crawler and the Brain will treat as the company, so
    a wrong value there is not cosmetic — it would seed the Company Brain with
    facts about a mail provider.
    """
    user_id = await a_user(db)

    workspace_id = await create_workspace_at_registration(
        db, user_id=user_id, email=f"bob@{provider}"
    )
    row = await workspace_row(db, workspace_id)

    assert row.domain is None
    assert row.name == "bob", "named from the local part, since there is no company domain"


async def test_a_company_domain_names_the_workspace(db: AsyncSession) -> None:
    user_id = await a_user(db)

    workspace_id = await create_workspace_at_registration(
        db, user_id=user_id, email="founder@acmetrading.om"
    )
    row = await workspace_row(db, workspace_id)

    assert row.name == "acmetrading.om"


async def test_an_explicit_name_wins_over_the_inferred_one(db: AsyncSession) -> None:
    """So the company-details step can set the real name (phase R2)."""
    user_id = await a_user(db)

    workspace_id = await create_workspace_at_registration(
        db, user_id=user_id, email="founder@acmetrading.om", workspace_name="Acme Trading LLC"
    )
    row = await workspace_row(db, workspace_id)

    assert row.name == "Acme Trading LLC"
    assert row.domain == "acmetrading.om", "the name is not the domain"


# ── The cost ADR 0013 accepts, asserted ────────────────────────


async def test_two_unverified_workspaces_may_hold_one_domain(db: AsyncSession) -> None:
    """This is the squatting consequence, and it is deliberate.

    The partial unique index constrains only verified rows, so two strangers
    registering at the same company each get their own unverified workspace naming
    it. Row-level security keeps their data apart — the domain string is a label
    here, never an authorisation input — and verification remains available to the
    real owner, who can still take the exclusive slot.

    Asserted rather than left as prose in the ADR, so that if someone later adds a
    unique constraint over all domains, registration breaking is a test failure
    rather than a support ticket.
    """
    first = await create_workspace_at_registration(
        db, user_id=await a_user(db), email="alice@contested.om"
    )
    second = await create_workspace_at_registration(
        db, user_id=await a_user(db), email="bob@contested.om"
    )

    assert first != second
    for workspace_id in (first, second):
        row = await workspace_row(db, workspace_id)
        assert row.domain == "contested.om"
        assert row.domain_verified_at is None


async def test_an_unverified_workspace_does_not_block_a_later_verified_one(
    db: AsyncSession,
) -> None:
    """The real owner must still be able to verify, or squatting would be terminal.

    The index only sees verified rows, so an unverified squatter is invisible to it.
    """
    await create_workspace_at_registration(
        db, user_id=await a_user(db), email="squatter@contested.om"
    )

    # What `create_workspace_for_claim` writes on the verified path.
    owner = await a_user(db)
    verified_id = uuid4()
    tenant = (
        await db.execute(text("INSERT INTO tenant (name) VALUES ('Real') RETURNING id"))
    ).scalar_one()
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(verified_id)}
    )
    await db.execute(
        text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            "                       domain_verified_at, verification_method)"
            " VALUES (:i, :i, :t, 'Real', 'contested.om', now(), 'dns_txt')"
        ),
        {"i": str(verified_id), "t": str(tenant)},
    )
    await db.execute(
        text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w, :u, 'owner', ARRAY['executive']::text[])"
        ),
        {"w": str(verified_id), "u": str(owner)},
    )

    row = await workspace_row(db, verified_id)
    assert row.domain_verified_at is not None, "the squatter did not block verification"

    members = (
        (
            await db.execute(
                text("SELECT user_id FROM membership WHERE workspace_id = :w"),
                {"w": str(verified_id)},
            )
        )
        .scalars()
        .all()
    )
    assert [UUID(str(m)) for m in members] == [owner], (
        "the verified workspace belongs to the person who verified it, not the squatter"
    )
