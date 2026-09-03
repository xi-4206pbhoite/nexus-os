"""The onboarding spine: resumable, department-driven, and honest about doubt.

`doc/12` §Phase 6. Three properties, and each replaces something the
single-page wizard could not do.

**Resumable** (Q28). Onboarding asks a founder for things they have to go and
find — a fiscal year start, a list of goals they have not written down. Any flow
that demands it in one sitting will be abandoned in the middle, and the abandoned
state has to be worth returning to.

**Department selection drives the product** (Q22, Q63). The seven directors are
not a menu of features; the selected set decides which dashboards exist at all.
Chief of Staff is automatic (Q24) because it consumes the others — a company
that selected none of them would have nothing for it to read.

**"Not sure yet" records an assumption, not a null.** This is the one that
matters most and is easiest to get wrong. A null says nobody was asked. An
assumption says somebody was asked, did not know, and the product proceeded on a
stated basis — which is a fact the Brain can later contradict with evidence, and
a null is not. It is also the difference between a blank dashboard tile and one
that says what it is assuming.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from tests.dburl import async_database_url

ASYNC_DB_URL = async_database_url()
requires_db = pytest.mark.requires_db


@pytest.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    assert ASYNC_DB_URL is not None
    monkeypatch.setenv("NEXUS_DATABASE_URL", ASYNC_DB_URL)
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "test-secret")
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    yield
    await get_engine().dispose()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


async def _workspace(db: AsyncSession) -> tuple[UUID, UUID]:
    """A workspace and its owner, committed."""
    user, tenant, ws = uuid4(), uuid4(), uuid4()
    await db.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"spine-{user.hex[:8]}@example.com"},
    )
    await db.execute(sa.text("INSERT INTO tenant (id, name) VALUES (:i,'T')"), {"i": str(tenant)})
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    await db.execute(
        sa.text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain,"
            " domain_verified_at) VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"spine-{ws.hex[:8]}.om"},
    )
    await db.execute(
        sa.text(
            "INSERT INTO membership (workspace_id, user_id, role, departments)"
            " VALUES (:w,:u,'owner', ARRAY['executive']::text[])"
        ),
        {"w": str(ws), "u": str(user)},
    )
    await db.commit()
    return user, ws


async def _cleanup(db: AsyncSession, user: UUID, ws: UUID) -> None:
    await db.execute(sa.text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    for statement in (
        "DELETE FROM onboarding_progress WHERE workspace_id = :w",
        "DELETE FROM workspace_department WHERE workspace_id = :w",
        "DELETE FROM onboarding_answer WHERE workspace_id = :w",
        "DELETE FROM audit_log WHERE workspace_id = :w",
        "DELETE FROM membership WHERE workspace_id = :w",
        "DELETE FROM workspace WHERE id = :w",
    ):
        await db.execute(sa.text(statement), {"w": str(ws)})
    await db.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
    await db.commit()


# ── Resumable ─────────────────────────────────────────────────


@requires_db
async def test_onboarding_progress_is_resumable(app_db: None) -> None:
    """Q28. Complete a stage, throw the session away, come back.

    The session is deliberately discarded rather than reused: progress that
    lived in memory or in a cookie would pass a test that kept them, and fail
    the founder who closed the tab.
    """
    from app.db import _unscoped_session
    from app.domain.progress import complete_stage, progress_for

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await complete_stage(db, workspace_id=ws, stage="company")
            await db.commit()
        finally:
            pass

    # A completely new session — nothing carried over but the database.
    async with _unscoped_session() as db:
        try:
            state = await progress_for(db, workspace_id=ws)
            assert "company" in state.completed
            assert state.current != "company", "resumed onto the stage just finished"
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_progress_does_not_go_backwards_on_a_repeat(app_db: None) -> None:
    """A double-clicked Continue, or a replayed POST, must not undo a stage.

    The obvious implementation — set `current` to the next stage — reverses a
    founder who has since moved on, which is the same class of defect as the
    double-click that broke workspace creation (finding #9).
    """
    from app.db import _unscoped_session
    from app.domain.progress import complete_stage, progress_for

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await complete_stage(db, workspace_id=ws, stage="company")
            await complete_stage(db, workspace_id=ws, stage="departments")
            await db.commit()
            ahead = (await progress_for(db, workspace_id=ws)).current

            await complete_stage(db, workspace_id=ws, stage="company")
            await db.commit()
            assert (await progress_for(db, workspace_id=ws)).current == ahead
        finally:
            await _cleanup(db, user, ws)


# ── Department selection drives the product ───────────────────


@requires_db
async def test_department_selection_drives_the_director_list(app_db: None) -> None:
    """Q22/Q63. Select two, and the product has three directors — those two and
    the Chief of Staff, which is automatic (Q24).

    Automatic because it *consumes* the others: a company that selected none
    would leave it reading nothing, so it is not a choice to offer.
    """
    from app.db import _unscoped_session
    from app.domain.departments import select_departments, selected_departments
    from app.domain.scopes import Department

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await select_departments(
                db, workspace_id=ws, departments={Department.MARKETING, Department.SALES}
            )
            await db.commit()

            chosen = await selected_departments(db, workspace_id=ws)
            assert Department.MARKETING in chosen
            assert Department.SALES in chosen
            assert Department.EXECUTIVE in chosen, "Chief of Staff must be automatic"
            assert Department.FINANCE not in chosen
        finally:
            await _cleanup(db, user, ws)


@requires_db
async def test_reselecting_replaces_rather_than_accumulates(app_db: None) -> None:
    """Changing your mind must remove what you deselected. Adding without
    removing would leave a director on the dashboard that nobody chose, and no
    screen through which to get rid of it."""
    from app.db import _unscoped_session
    from app.domain.departments import select_departments, selected_departments
    from app.domain.scopes import Department

    async with _unscoped_session() as db:
        user, ws = await _workspace(db)
        try:
            await select_departments(
                db, workspace_id=ws, departments={Department.MARKETING, Department.SALES}
            )
            await db.commit()
            await select_departments(db, workspace_id=ws, departments={Department.FINANCE})
            await db.commit()

            chosen = await selected_departments(db, workspace_id=ws)
            assert Department.FINANCE in chosen
            assert Department.MARKETING not in chosen
        finally:
            await _cleanup(db, user, ws)


# ── "Not sure yet" is an assumption, not a null ───────────────


def test_the_company_stage_asks_five_questions() -> None:
    """Q19. Five, and they are the five a founder can answer without going to
    look anything up except the fiscal year."""
    from app.domain.onboarding import COMPANY_QUESTIONS

    keys = [q.key for q in COMPANY_QUESTIONS]
    assert len(keys) == 5, f"expected five company questions, got {keys}"
    assert set(keys) == {
        "what_you_sell",
        "ideal_customer",
        "top_goals",
        "biggest_challenges",
        "fiscal_year_start",
    }


def test_every_company_question_offers_not_sure_yet() -> None:
    """Because a founder who cannot answer must be able to proceed *and* leave a
    trace of what was assumed on their behalf."""
    from app.domain.onboarding import COMPANY_QUESTIONS

    missing = [q.key for q in COMPANY_QUESTIONS if not q.assumption_when_unsure]
    assert missing == [], f"these have no assumption to fall back on: {missing}"


def test_not_sure_yet_records_an_assumption_not_a_null() -> None:
    """The property this whole design turns on.

    A null says nobody was asked. An assumption says somebody was asked, did not
    know, and the product proceeded on a stated basis — which the Brain can
    later contradict with evidence, and a null cannot. It is also the difference
    between a blank tile and one that says what it is assuming.
    """
    from app.domain.onboarding import BY_KEY, resolve_answer

    stored = resolve_answer(BY_KEY["ideal_customer"], value=None, unsure=True)

    assert stored.value is not None, "'not sure yet' stored a null"
    assert stored.is_assumption is True
    assert stored.value == BY_KEY["ideal_customer"].assumption_when_unsure
    # And an actual answer is not marked as one.
    given = resolve_answer(BY_KEY["ideal_customer"], value="Mid-market logistics", unsure=False)
    assert given.is_assumption is False
    assert given.value == "Mid-market logistics"


def test_a_crawl_confirmable_question_is_not_asked_here() -> None:
    """Q20's crawl-then-confirm posture. Industry is the first such field.

    Asking a founder something the crawl will tell us anyway spends the scarcest
    thing onboarding has — their patience — on a question we can answer
    ourselves and have them *confirm* at the review gate.
    """
    from app.domain.onboarding import COMPANY_QUESTIONS, CONFIRMABLE_FROM_CRAWL

    assert CONFIRMABLE_FROM_CRAWL, "nothing is marked confirmable; Q20 is unimplemented"
    asked = {q.key for q in COMPANY_QUESTIONS}
    for question in CONFIRMABLE_FROM_CRAWL:
        assert question.key not in asked, (
            f"{question.key} is confirmable from the crawl and is still being asked"
        )
