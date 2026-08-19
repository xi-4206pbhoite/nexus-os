"""Two answers that are not `onboarding_answer` rows.

`onboarding_answer` is unique on `(workspace_id, question_key)` — it stores
*workspace* facts. Two things the registration flow collects are not:

- **`your_name`** is per user. As an ordinary answer, two members of one workspace
  would contend for a single row and the second would silently overwrite the first.
- **`company_name`** already exists, as `workspace.name`. Writing it to
  `onboarding_answer` as well would give one fact two homes that can disagree —
  the drift that produced `ReviewState`'s wrong spelling and a `document.status`
  of `indexed` nothing had earned.

So both write through to their real column. What has to be true, and is asserted
here against a real database because these are UPDATEs that row-level security and
a `WHERE` clause are the only things aiming:

- the value lands in the column, and **no** `onboarding_answer` row appears;
- the wizard reads it back, or a reload would ask the user to type their name again;
- `your_name` is per user — two members do not overwrite each other;
- neither UPDATE can be aimed at another workspace or another account, because
  neither takes an id from the request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.onboarding import BY_KEY, CATALOGUE, Sink
from app.domain.scopes import Department, Role
from app.domain.session import ScopedSession
from app.routes.setup import store_answer
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
pytestmark = pytest.mark.skipif(
    ASYNC_DB_URL is None,
    reason="No NEXUS_DATABASE_URL — a write-through to a real column needs a real database",
)


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


async def a_workspace(db: AsyncSession, *, name: str = "acmetrading.om") -> tuple[UUID, UUID]:
    """A workspace with one owner, and the GUC set as a request would."""
    workspace_id, user_id = uuid4(), uuid4()
    tenant = (
        await db.execute(text("INSERT INTO tenant (name) VALUES (:n) RETURNING id"), {"n": name})
    ).scalar_one()
    await db.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i, :e)"),
        {"i": str(user_id), "e": f"sink-{user_id}@example.test"},
    )
    await db.execute(
        text(
            "SELECT set_config('nexus.workspace_id', :w, true),"
            "       set_config('nexus.user_id', :u, true)"
        ),
        {"w": str(workspace_id), "u": str(user_id)},
    )
    await db.execute(
        text("INSERT INTO workspace (id, workspace_id, tenant_id, name) VALUES (:i, :i, :t, :n)"),
        {"i": str(workspace_id), "t": str(tenant), "n": name},
    )
    await db.execute(
        text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w, :u, 'owner', ARRAY['executive']::text[])"
        ),
        {"w": str(workspace_id), "u": str(user_id)},
    )
    return workspace_id, user_id


def scope_for(workspace_id: UUID, user_id: UUID) -> ScopedSession:
    return ScopedSession(
        user_id=user_id,
        workspace_id=workspace_id,
        tenant_id=uuid4(),
        role=Role.OWNER,
        departments=frozenset({Department.EXECUTIVE}),
    )


async def answer_rows(db: AsyncSession, key: str) -> int:
    return int(
        (
            await db.execute(
                text("SELECT count(*) FROM onboarding_answer WHERE question_key = :k"), {"k": key}
            )
        ).scalar_one()
    )


# ── The catalogue's own claim ──────────────────────────────────


def test_exactly_two_questions_are_sink_backed() -> None:
    """An exact set, so a third write-through has to be a deliberate decision.

    Every other question is an `onboarding_answer` row, which is where the scope
    tagging and the review path live. Routing one elsewhere skips both.
    """
    sinked = {q.key: q.sink for q in CATALOGUE if q.sink is not Sink.ANSWER}
    assert sinked == {
        "your_name": Sink.USER_DISPLAY_NAME,
        "company_name": Sink.WORKSPACE_NAME,
    }


# ── The company's name has one home ────────────────────────────


async def test_the_company_name_updates_the_workspace(db: AsyncSession) -> None:
    workspace_id, user_id = await a_workspace(db)
    scope = scope_for(workspace_id, user_id)

    await store_answer(
        db, caller=scope, question=BY_KEY["company_name"], value="  Acme Trading LLC  "
    )

    name = (
        await db.execute(text("SELECT name FROM workspace WHERE id = :i"), {"i": str(workspace_id)})
    ).scalar_one()
    assert name == "Acme Trading LLC", "trimmed, since a leading space would render"


async def test_the_company_name_writes_no_answer_row(db: AsyncSession) -> None:
    """The whole point of the sink. Two homes for one fact is the failure mode."""
    workspace_id, user_id = await a_workspace(db)

    await store_answer(
        db,
        caller=scope_for(workspace_id, user_id),
        question=BY_KEY["company_name"],
        value="Acme Trading LLC",
    )

    assert await answer_rows(db, "company_name") == 0


async def test_renaming_replaces_rather_than_accumulates(db: AsyncSession) -> None:
    """Onboarding is revisitable, so this is the ordinary case, not a conflict."""
    workspace_id, user_id = await a_workspace(db)
    scope = scope_for(workspace_id, user_id)

    for value in ("First Name LLC", "Second Name LLC"):
        await store_answer(db, caller=scope, question=BY_KEY["company_name"], value=value)

    name = (
        await db.execute(text("SELECT name FROM workspace WHERE id = :i"), {"i": str(workspace_id)})
    ).scalar_one()
    assert name == "Second Name LLC"


# ── A person's name is theirs alone ────────────────────────────


async def test_your_name_updates_the_calling_user(db: AsyncSession) -> None:
    workspace_id, user_id = await a_workspace(db)

    await store_answer(
        db, caller=scope_for(workspace_id, user_id), question=BY_KEY["your_name"], value="Parul"
    )

    display = (
        await db.execute(
            text("SELECT display_name FROM app_user WHERE id = :i"), {"i": str(user_id)}
        )
    ).scalar_one()
    assert display == "Parul"
    assert await answer_rows(db, "your_name") == 0


async def test_two_members_do_not_overwrite_each_others_names(db: AsyncSession) -> None:
    """The reason this is not an ordinary answer.

    `onboarding_answer` is unique on `(workspace_id, question_key)`, so as a plain
    answer the second person to fill the form in would have silently replaced the
    first person's name with their own.
    """
    workspace_id, first = await a_workspace(db)

    second = uuid4()
    await db.execute(
        text("INSERT INTO app_user (id, email) VALUES (:i, :e)"),
        {"i": str(second), "e": f"sink-{second}@example.test"},
    )
    await db.execute(
        text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w, :u, 'executive', ARRAY['executive']::text[])"
        ),
        {"w": str(workspace_id), "u": str(second)},
    )

    await store_answer(
        db, caller=scope_for(workspace_id, first), question=BY_KEY["your_name"], value="Alice"
    )
    await store_answer(
        db, caller=scope_for(workspace_id, second), question=BY_KEY["your_name"], value="Bob"
    )

    names = dict(
        (
            await db.execute(
                text("SELECT id, display_name FROM app_user WHERE id IN (:a, :b)"),
                {"a": str(first), "b": str(second)},
            )
        ).all()
    )
    assert names[first] == "Alice"
    assert names[second] == "Bob"


# ── Neither UPDATE can be aimed elsewhere ──────────────────────


async def test_the_workspace_update_cannot_reach_another_workspace(db: AsyncSession) -> None:
    """Row-level security is the aim, not our care.

    `store_answer` passes `caller.workspace_id`, which is resolved server-side, and
    the policy's USING clause compares it to the GUC. Setting the GUC to workspace A
    and asking to rename workspace B changes nothing — there is no request field
    that could do this, so the test constructs the mismatch by hand.
    """
    first_id, user_id = await a_workspace(db, name="First")
    other_id = uuid4()
    tenant = (
        await db.execute(text("INSERT INTO tenant (name) VALUES ('Other') RETURNING id"))
    ).scalar_one()
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(other_id)}
    )
    await db.execute(
        text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name) VALUES (:i, :i, :t, 'Other')"
        ),
        {"i": str(other_id), "t": str(tenant)},
    )

    # Back to the first workspace's context, then try to rename the second.
    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(first_id)}
    )
    forged = ScopedSession(
        user_id=user_id,
        workspace_id=other_id,  # not the GUC's workspace
        tenant_id=uuid4(),
        role=Role.OWNER,
        departments=frozenset({Department.EXECUTIVE}),
    )
    await store_answer(db, caller=forged, question=BY_KEY["company_name"], value="Renamed")

    await db.execute(
        text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(other_id)}
    )
    name = (
        await db.execute(text("SELECT name FROM workspace WHERE id = :i"), {"i": str(other_id)})
    ).scalar_one()
    assert name == "Other", "RLS refused the cross-workspace rename"
