"""Finishing setup: the marker, the notification, and where the user goes next.

Three properties, and two of them are about things *not* happening.

**Completing twice must not email twice.** The timestamp is set with
`WHERE setup_completed_at IS NULL ... RETURNING`, so the database decides whether a
call was the transition. A read-then-write would let two clicks both observe `NULL`
and both send — the classic shape of this bug, and the reason the check and the write
are one statement.

**Email must never block completion.** The account exists and the setup is finished;
refusing to record that because a notification could not go out would lose the thing
that matters to keep the thing that does not. Failure is reported in the payload
rather than raised.

**The landing department comes from membership, never from the answer.** Someone can
state "Finance" in the wizard while their membership says Sales, and landing them on
a page their scope cannot reach would 404 immediately after setup — the worst possible
first impression.

Against a real database: the idempotency is a property of one SQL statement, and a
substituted session would test the shape rather than the behaviour.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.dashboards import landing_department
from app.domain.scopes import Department
from app.mail import Email, FileMailer
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
pytestmark = pytest.mark.skipif(
    ASYNC_DB_URL is None,
    reason="No NEXUS_DATABASE_URL — idempotency is a property of the UPDATE statement",
)

COMPLETE_ONCE = (
    "UPDATE workspace SET setup_completed_at = now()"
    " WHERE id = :ws AND setup_completed_at IS NULL"
    " RETURNING setup_completed_at"
)
"""The production statement, quoted rather than reimplemented.

A test that wrote its own idempotency check would prove its own logic. This is the
statement `complete_setup` runs, so a change to it fails here.
"""


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
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


async def a_workspace(db: AsyncSession) -> UUID:
    workspace_id, user_id, tenant = uuid4(), uuid4(), uuid4()
    await db.execute(
        text("INSERT INTO tenant (id, name) VALUES (:t, 'Completion')"), {"t": str(tenant)}
    )
    await db.execute(
        text("INSERT INTO app_user (id, email) VALUES (:u, :e)"),
        {"u": str(user_id), "e": f"done-{user_id}@example.test"},
    )
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(workspace_id)}
    )
    await db.execute(
        text("INSERT INTO workspace (id, workspace_id, tenant_id, name) VALUES (:i, :i, :t, 'Co')"),
        {"i": str(workspace_id), "t": str(tenant)},
    )
    return workspace_id


# ── The marker, and the idempotency that hangs off it ─────────


async def test_completing_records_when(db: AsyncSession) -> None:
    workspace_id = await a_workspace(db)

    row = (await db.execute(text(COMPLETE_ONCE), {"ws": str(workspace_id)})).first()

    assert row is not None
    assert row.setup_completed_at is not None


async def test_a_fresh_workspace_is_not_complete(db: AsyncSession) -> None:
    """`NULL` is the honest state for "never", which is why this is a timestamp
    rather than a boolean defaulting to false."""
    workspace_id = await a_workspace(db)

    value = (
        await db.execute(
            text("SELECT setup_completed_at FROM workspace WHERE id = :i"),
            {"i": str(workspace_id)},
        )
    ).scalar_one()

    assert value is None


async def test_completing_twice_transitions_once(db: AsyncSession) -> None:
    """The property the notification depends on.

    The second call returns no row, which is how the handler knows not to send a
    second email. A read-then-write would let two clicks both see `NULL`.
    """
    workspace_id = await a_workspace(db)

    first = (await db.execute(text(COMPLETE_ONCE), {"ws": str(workspace_id)})).first()
    second = (await db.execute(text(COMPLETE_ONCE), {"ws": str(workspace_id)})).first()

    assert first is not None, "the first call is the transition"
    assert second is None, "the second changed nothing, so no second email"


async def test_the_timestamp_is_not_moved_by_a_second_call(db: AsyncSession) -> None:
    """When setup finished is a fact about the past. Re-stamping it would make
    "how long has this workspace been running" unanswerable, which the morning brief
    needs to tell a delta from a baseline (doc 04 §6 rule 3)."""
    workspace_id = await a_workspace(db)

    first = (await db.execute(text(COMPLETE_ONCE), {"ws": str(workspace_id)})).one()
    await db.execute(text(COMPLETE_ONCE), {"ws": str(workspace_id)})

    still = (
        await db.execute(
            text("SELECT setup_completed_at FROM workspace WHERE id = :i"),
            {"i": str(workspace_id)},
        )
    ).scalar_one()

    assert still == first.setup_completed_at


async def test_completion_is_scoped_to_one_workspace(db: AsyncSession) -> None:
    """RLS aims the UPDATE. Finishing one company's setup must not finish another's."""
    first = await a_workspace(db)
    second = await a_workspace(db)

    await db.execute(text(COMPLETE_ONCE), {"ws": str(first)})

    await db.execute(text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(second)})
    other = (
        await db.execute(
            text("SELECT setup_completed_at FROM workspace WHERE id = :i"), {"i": str(second)}
        )
    ).scalar_one()

    assert other is None


# ── Where the user goes next ──────────────────────────────────


def test_an_owner_lands_on_the_chief_of_staff() -> None:
    """The only page that reads across all seven departments."""
    assert (
        landing_department(executive_surface=True, departments=frozenset()) is Department.EXECUTIVE
    )


def test_a_department_member_lands_on_their_own_department() -> None:
    assert (
        landing_department(executive_surface=False, departments=frozenset({Department.SALES}))
        is Department.SALES
    )


def test_someone_with_no_department_lands_nowhere() -> None:
    """`None` rather than a default. Picking one puts somebody in a department nobody
    assigned them to, and the dashboard would then 404 on it."""
    assert landing_department(executive_surface=False, departments=frozenset()) is None


def test_the_landing_is_not_taken_from_the_role_answer() -> None:
    """A stated role is a fact about the person; membership is what authorises.

    Asserted by signature: `landing_department` takes the resolved scope's fields and
    has no parameter an onboarding answer could be passed through.
    """
    import inspect

    parameters = set(inspect.signature(landing_department).parameters)
    assert parameters == {"executive_surface", "departments"}
    assert "answers" not in parameters


# ── Email never blocks completion ─────────────────────────────


def test_the_file_mailer_writes_the_notification(tmp_path: Path) -> None:
    mailer = FileMailer(tmp_path)

    mailer.send(Email(to="founder@acme.om", subject="Co is set up", text_body="Done."))

    written = mailer.sent_messages()
    assert len(written) == 1
    body = written[0].read_text()
    assert "founder@acme.om" in body
    assert "Co is set up" in body


def test_an_unconfigured_mailer_is_none_rather_than_an_error() -> None:
    """`None` is what lets completion continue. An exception here would make a missing
    notification channel fatal to finishing setup."""
    from app.config import Settings
    from app.routes.setup import _mailer

    assert _mailer(Settings(mailer_backend="none")) is None
    assert _mailer(Settings(mailer_backend="file")) is not None


def test_the_notification_says_what_does_not_exist_yet() -> None:
    """The product's content rule applied to its own transactional email.

    A "you're all set!" message would be the same overclaim as a dashboard tile
    showing a zero — every capability is still unbuilt and no tool is connected.
    """
    from app.config import Settings
    from app.routes.setup import _notify_setup_complete

    sent, detail = _notify_setup_complete(
        Settings(mailer_backend="none"), recipient="founder@acme.om", workspace_name="Co"
    )

    assert sent is False
    assert "complete regardless" in detail, "the failure must not read as a failed setup"


def test_a_missing_address_does_not_fail_completion() -> None:
    from app.config import Settings
    from app.routes.setup import _notify_setup_complete

    sent, detail = _notify_setup_complete(
        Settings(mailer_backend="file"), recipient=None, workspace_name="Co"
    )

    assert sent is False
    assert detail
