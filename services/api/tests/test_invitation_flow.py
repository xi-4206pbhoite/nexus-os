"""Joining a workspace, against a real database.

`test_persona_and_invitations.py` proves the *table* carries the role and the
inviter. This proves the *flow* honours it: that acceptance copies what the
inviter set, that a link works exactly once, and that the two row-level security
policies this flow needed — migrations 0008 and 0009 — expose precisely one row
set each and nothing more.

Against Postgres rather than a substitute, because every assertion here is about
what a policy does, and a fake would only tell us what we believe it does. Two
of these tests would have failed before the migrations they cover existed, and
one of them — `test_a_member_can_see_their_own_workspace` — is the reason every
workspace-scoped route in the product was returning 403 to its own members.

Everything runs inside one transaction that is rolled back, so the suite leaves
nothing behind on a shared database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth import invitations as invites
from app.auth.service import memberships_for_user
from app.auth.tokens import hash_token
from app.domain.onboarding import BY_KEY
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.routes.setup import store_answer
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.skipif(ASYNC_DB_URL is None, reason="No NEXUS_DATABASE_URL")

pytestmark = requires_db


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that never commits."""
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


# ── Seeding ───────────────────────────────────────────────────


async def make_user(db: AsyncSession, email: str | None = None) -> tuple[UUID, str]:
    user_id = uuid4()
    address = email or f"u-{user_id}@example.com"
    await db.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i, :e)"),
        {"i": str(user_id), "e": address},
    )
    return user_id, address


async def set_scope(db: AsyncSession, *, workspace_id: UUID | None, user_id: UUID | None) -> None:
    """What `scoped_connection` does, spelled out so each test states its context."""
    await db.execute(
        text(
            "SELECT set_config('nexus.workspace_id', :ws, true),"
            "       set_config('nexus.user_id', :u, true)"
        ),
        {"ws": str(workspace_id or ""), "u": str(user_id or "")},
    )


async def make_workspace(db: AsyncSession, *, owner_id: UUID) -> UUID:
    """A workspace with an Owner, seeded the way the application now does it.

    `id` and `workspace_id` are the same value and the GUC is set first — which
    is what migration 0002 means by "`workspace_id` mirrors `id`", and what
    `create_workspace_for_claim` failed to do until this milestone.
    """
    tenant_id = (
        await db.execute(text("INSERT INTO tenant (name) VALUES ('Test Co') RETURNING id"))
    ).scalar_one()
    workspace_id = uuid4()

    await set_scope(db, workspace_id=workspace_id, user_id=owner_id)
    await db.execute(
        text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i, :i, :t, 'Test Co', :d, now())"
        ),
        {"i": str(workspace_id), "t": str(tenant_id), "d": f"t-{workspace_id}.example"},
    )
    await db.execute(
        text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w, :u, 'owner', ARRAY['executive']::text[])"
        ),
        {"w": str(workspace_id), "u": str(owner_id)},
    )
    return workspace_id


def owner_scope(*, user_id: UUID, workspace_id: UUID) -> ScopedSession:
    return ScopedSession(
        user_id=user_id,
        tenant_id=uuid4(),
        workspace_id=workspace_id,
        role=Role.OWNER,
        departments=frozenset({Department.EXECUTIVE}),
    )


async def role_of(db: AsyncSession, *, workspace_id: UUID, user_id: UUID) -> tuple[str, list[str]]:
    row = (
        await db.execute(
            text(
                "SELECT role, departments FROM membership"
                " WHERE workspace_id = :w AND user_id = :u AND revoked_at IS NULL"
            ),
            {"w": str(workspace_id), "u": str(user_id)},
        )
    ).first()
    assert row is not None, "no membership row"
    return str(row.role), sorted(row.departments or [])


# ── Migration 0008: a member can see their own workspace ──────


async def test_a_member_can_see_their_own_workspace(db: AsyncSession) -> None:
    """The bug this closes: `memberships_for_user` joins `membership` to
    `workspace`, and `workspace` was reachable only with the workspace GUC set —
    which login cannot do, because which workspace is what it is trying to find
    out. It returned an empty list for genuine members, so `current_scope` gave
    every one of them 403 and no workspace-scoped route was reachable at all.
    """
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)

    # Exactly login's position: no workspace context, only an identity.
    await set_scope(db, workspace_id=None, user_id=None)
    memberships = await memberships_for_user(db, user_id=owner_id)

    assert [m.workspace_id for m in memberships] == [workspace_id]
    assert memberships[0].role is Role.OWNER


async def test_a_stranger_cannot_see_that_workspace(db: AsyncSession) -> None:
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    stranger_id, _ = await make_user(db)

    await set_scope(db, workspace_id=None, user_id=None)
    assert await memberships_for_user(db, user_id=stranger_id) == []

    await set_scope(db, workspace_id=None, user_id=stranger_id)
    visible = (
        await db.execute(
            text("SELECT count(*) FROM workspace WHERE id = :w"), {"w": str(workspace_id)}
        )
    ).scalar_one()
    assert visible == 0


async def test_revoking_a_membership_hides_the_workspace_immediately(db: AsyncSession) -> None:
    """Doc 06 §4.15 — a role change takes effect for live queries, so the
    predicate has to test `revoked_at`, not merely the row's existence."""
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)

    await db.execute(
        text("UPDATE membership SET revoked_at = now() WHERE workspace_id = :w AND user_id = :u"),
        {"w": str(workspace_id), "u": str(owner_id)},
    )

    await set_scope(db, workspace_id=None, user_id=None)
    assert await memberships_for_user(db, user_id=owner_id) == []


# ── Migration 0009: an invitation is found by its token ───────


async def test_an_invitation_is_invisible_without_the_token(db: AsyncSession) -> None:
    """The default. Without a workspace context or a token hash, nothing."""
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email="new@example.com",
        role=Role.VIEWER,
        departments=frozenset(),
    )

    await set_scope(db, workspace_id=None, user_id=None)
    count = (await db.execute(text("SELECT count(*) FROM invitation"))).scalar_one()
    assert count == 0


async def test_the_token_policy_exposes_exactly_the_matching_row(db: AsyncSession) -> None:
    """Visibility follows possession of the token and nothing else.

    Presenting the hash discloses nothing new — the hash is derived from the
    token, and the token is the credential. A hash that matches no row matches
    no row; there is no partial match to work from.
    """
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    first = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email="one@example.com",
        role=Role.VIEWER,
        departments=frozenset(),
    )
    await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email="two@example.com",
        role=Role.VIEWER,
        departments=frozenset(),
    )

    await set_scope(db, workspace_id=None, user_id=None)
    await db.execute(
        text("SELECT set_config('nexus.invitation_token_hash', :h, true)"),
        {"h": hash_token(first.token)},
    )
    rows = (await db.execute(text("SELECT email FROM invitation"))).scalars().all()
    assert rows == ["one@example.com"]

    await db.execute(
        text("SELECT set_config('nexus.invitation_token_hash', :h, true)"),
        {"h": hash_token("a-token-that-was-never-issued")},
    )
    assert (await db.execute(text("SELECT count(*) FROM invitation"))).scalar_one() == 0


# ── Acceptance copies the role (doc 06 §2.2) ──────────────────


async def test_acceptance_copies_the_role_the_inviter_set(db: AsyncSession) -> None:
    """*"Every subsequent user's role is set by the inviter, never
    self-declared at acceptance."* The accepting user supplies a token and an
    identity; the role and department come off the row the inviter wrote."""
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    joiner_id, joiner_email = await make_user(db)

    issued = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=joiner_email,
        role=Role.CONTRIBUTOR,
        departments=frozenset({Department.SALES}),
    )

    result = await invites.accept(db, token=issued.token, user_id=joiner_id)

    assert result.outcome is invites.AcceptOutcome.ACCEPTED
    assert result.workspace_id == workspace_id
    assert await role_of(db, workspace_id=workspace_id, user_id=joiner_id) == (
        "contributor",
        ["sales"],
    )


async def test_a_link_works_once(db: AsyncSession) -> None:
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    joiner_id, joiner_email = await make_user(db)

    issued = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=joiner_email,
        role=Role.VIEWER,
        departments=frozenset(),
    )

    assert (await invites.accept(db, token=issued.token, user_id=joiner_id)).outcome is (
        invites.AcceptOutcome.ACCEPTED
    )
    assert (await invites.accept(db, token=issued.token, user_id=joiner_id)).outcome is (
        invites.AcceptOutcome.UNUSABLE
    )


async def test_accepting_while_signed_in_as_somebody_else_is_refused(db: AsyncSession) -> None:
    """A forwarded link must not seat the person it was forwarded to in a role
    that was chosen for someone else."""
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    _, invited_email = await make_user(db, email=f"invited-{uuid4()}@example.com")
    bystander_id, _ = await make_user(db)

    issued = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=invited_email,
        role=Role.EXECUTIVE,
        departments=frozenset({Department.EXECUTIVE}),
    )

    result = await invites.accept(db, token=issued.token, user_id=bystander_id)

    assert result.outcome is invites.AcceptOutcome.WRONG_ACCOUNT
    await set_scope(db, workspace_id=workspace_id, user_id=owner_id)
    seated = (
        await db.execute(
            text("SELECT count(*) FROM membership WHERE user_id = :u"), {"u": str(bystander_id)}
        )
    ).scalar_one()
    assert seated == 0


async def test_a_revoked_invitation_cannot_be_accepted(db: AsyncSession) -> None:
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    joiner_id, joiner_email = await make_user(db)

    issued = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=joiner_email,
        role=Role.VIEWER,
        departments=frozenset(),
    )
    assert await invites.revoke(db, invitation_id=issued.invitation.id)

    assert (await invites.accept(db, token=issued.token, user_id=joiner_id)).outcome is (
        invites.AcceptOutcome.UNUSABLE
    )


async def test_an_expired_invitation_cannot_be_accepted(db: AsyncSession) -> None:
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    joiner_id, joiner_email = await make_user(db)

    issued = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=joiner_email,
        role=Role.VIEWER,
        departments=frozenset(),
        ttl=timedelta(seconds=-1),
    )

    assert (await invites.accept(db, token=issued.token, user_id=joiner_id)).outcome is (
        invites.AcceptOutcome.UNUSABLE
    )


async def test_re_inviting_the_same_person_retires_the_earlier_link(db: AsyncSession) -> None:
    """Two live links for one person is two roles they might end up with,
    decided by which email they happen to open."""
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    joiner_id, joiner_email = await make_user(db)

    first = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=joiner_email,
        role=Role.VIEWER,
        departments=frozenset(),
    )
    second = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=joiner_email,
        role=Role.DEPARTMENT_MANAGER,
        departments=frozenset({Department.MARKETING}),
    )

    assert (await invites.accept(db, token=first.token, user_id=joiner_id)).outcome is (
        invites.AcceptOutcome.UNUSABLE
    )
    assert (await invites.accept(db, token=second.token, user_id=joiner_id)).outcome is (
        invites.AcceptOutcome.ACCEPTED
    )
    assert await role_of(db, workspace_id=workspace_id, user_id=joiner_id) == (
        "department_manager",
        ["marketing"],
    )


async def test_an_existing_member_keeps_the_role_they_already_hold(db: AsyncSession) -> None:
    """Changing a live member's role from a link is a role change (doc 06
    §4.15), not an invitation. Doing it silently is how someone is demoted by an
    email they did not read."""
    owner_id, owner_email = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)

    issued = await invites.issue(
        db,
        workspace_id=workspace_id,
        invited_by_user_id=owner_id,
        email=owner_email,
        role=Role.VIEWER,
        departments=frozenset(),
    )
    result = await invites.accept(db, token=issued.token, user_id=owner_id)

    assert result.outcome is invites.AcceptOutcome.ALREADY_A_MEMBER
    assert await role_of(db, workspace_id=workspace_id, user_id=owner_id) == (
        "owner",
        ["executive"],
    )


# ── Answers land at the catalogue's classification ────────────


async def test_an_answer_is_stored_at_the_scope_the_catalogue_names(db: AsyncSession) -> None:
    """Doc 06 §2.5 — *"tag them at capture"*, through the write path the route
    actually uses rather than through a copy of its SQL."""
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    caller = owner_scope(user_id=owner_id, workspace_id=workspace_id)

    await store_answer(db, caller=caller, question=BY_KEY["average_deal_size"], value=12500.0)
    await store_answer(db, caller=caller, question=BY_KEY["stated_purpose"], value="Grow exports")

    found = (
        (await db.execute(text("SELECT question_key, scope FROM onboarding_answer")))
        .mappings()
        .all()
    )
    rows = {r["question_key"]: r["scope"] for r in found}

    assert rows["average_deal_size"] == "L3"
    assert rows["stated_purpose"] == "L2"


async def test_answering_twice_updates_rather_than_duplicating(db: AsyncSession) -> None:
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    caller = owner_scope(user_id=owner_id, workspace_id=workspace_id)

    await store_answer(db, caller=caller, question=BY_KEY["currency"], value="INR")
    await store_answer(db, caller=caller, question=BY_KEY["currency"], value="EUR")

    rows = (
        (
            await db.execute(
                text("SELECT value FROM onboarding_answer WHERE question_key = 'currency'")
            )
        )
        .scalars()
        .all()
    )
    assert rows == ["EUR"]


async def test_an_l3_answer_carries_its_department(db: AsyncSession) -> None:
    """The CHECK constraint refuses L3 with no department, so this asserts the
    write path satisfies it rather than relying on the constraint to fire."""
    owner_id, _ = await make_user(db)
    workspace_id = await make_workspace(db, owner_id=owner_id)
    caller = owner_scope(user_id=owner_id, workspace_id=workspace_id)

    await store_answer(
        db, caller=caller, question=BY_KEY["monthly_marketing_budget"], value=40000.0
    )

    department = (
        await db.execute(
            text(
                "SELECT department FROM onboarding_answer"
                " WHERE question_key = 'monthly_marketing_budget'"
            )
        )
    ).scalar_one()
    assert department == "finance"
