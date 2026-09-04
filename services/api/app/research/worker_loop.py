"""The worker's loop: claim a run, dispatch its sources, record each outcome.

Everything it needs already exists — `CLAIM_SQL` takes a run without two workers
taking the same one, `crawl_site` returns an outcome instead of raising, and
`state_for` derives the run's state from its sources. This is the wiring, and
its whole job is to preserve Q56 across the join.

**Each source is written independently, as it finishes.** Not batched at the
end: a worker that crashes after five of six sources should leave five results
behind, and the founder watching the progress screen should see them arrive
rather than nothing for four minutes and then everything.
"""

from __future__ import annotations

import asyncio
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.domain.research import (
    CLAIM_SQL,
    STALE_AFTER_MINUTES,
    SourceKind,
    SourceState,
    state_for,
)
from app.logging import get_logger
from app.research.runner import CrawlOutcome, crawl_site
from app.retrieval.scoped import apply_workspace_scope

log = get_logger(__name__)

CONCURRENT_SOURCES: Final = 3
"""How many sources run at once. Three rather than six because they share an
outbound connection budget and a database pool — running all six flat out makes
the slowest one slower, and none of them is the bottleneck the founder feels."""

UNAVAILABLE_NO_CREDENTIALS: Final = "unavailable: no_credentials"
"""Q53/D2. Keyword data **stays locked** rather than estimated. An estimate
that looks like a measurement is the one thing this product cannot ship — and it
would look exactly like the real thing on the screen."""


async def _record(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    kind: SourceKind,
    outcome: CrawlOutcome,
) -> None:
    """Write one source's outcome.

    **Scopes first, every time.** The GUC is transaction-local, so the commit
    that ended the previous statement also ended the scope — and an UPDATE under
    RLS with no policy match affects **zero rows and raises nothing**. The
    source stays `running` forever, the run never finishes, and there is nothing
    in any log. Found exactly that way.
    """
    await apply_workspace_scope(db, workspace_id)
    await db.execute(
        text(
            "UPDATE research_source"
            "   SET state = :s, error_reason = :e, finished_at = now()"
            " WHERE run_id = :r AND kind = :k"
        ),
        {
            "s": outcome.state.value,
            "e": outcome.error_reason,
            "r": str(run_id),
            "k": kind.value,
        },
    )
    await db.commit()


async def _run_source(
    db: AsyncSession, *, workspace_id: UUID, run_id: UUID, kind: SourceKind, seeds: list[str]
) -> None:
    """One source, start to finish. **Never raises.**

    The `except` is deliberately broad. Q56 says one source failing must not
    fail the run, and a source that raises an exception nobody anticipated would
    do exactly that — so anything unhandled becomes a failed source with a
    reason, and the other five carry on.
    """
    await db.execute(
        text(
            "UPDATE research_source SET state='running', started_at=now()"
            " WHERE run_id=:r AND kind=:k"
        ),
        {"r": str(run_id), "k": kind.value},
    )
    await db.commit()

    try:
        if kind is SourceKind.CRAWL:
            outcome = await crawl_site(seeds)
        elif kind is SourceKind.KEYWORDS:
            # Not implemented, and **not estimated** (Q53/D2).
            outcome = CrawlOutcome(
                state=SourceState.FAILED, error_reason=UNAVAILABLE_NO_CREDENTIALS
            )
        else:
            # The remaining four have no implementation yet. `skipped` rather
            # than `failed`: nothing broke, we have not built it, and telling a
            # founder their competitors research failed would be blaming them
            # for our backlog.
            outcome = CrawlOutcome(state=SourceState.SKIPPED)
    except Exception as exc:
        log.warning("research.source_crashed", kind=kind.value, error=str(exc))
        outcome = CrawlOutcome(
            state=SourceState.FAILED,
            error_reason="This step did not finish. The rest of your research is unaffected.",
        )

    await _record(db, workspace_id=workspace_id, run_id=run_id, kind=kind, outcome=outcome)


async def process_one_run(db: AsyncSession) -> UUID | None:
    """Claim a run and finish it, or return `None` if there is nothing queued.

    **The session must be able to see runs across workspaces**, and the app role
    cannot: `research_run` is row-level secured on `nexus.workspace_id`, so an
    app-role connection with no GUC set sees nothing and this returns `None`
    forever — a worker that looks healthy and processes nothing.

    In production this belongs on the **`nexus_jobs` role** (ADR 0018), which
    exists for exactly this shape: maintenance work that must span tenants,
    holding a narrow policy rather than `BYPASSRLS`. `research_run` does not yet
    grant it — see finding #25. Until it does, a caller must scope the session
    itself, which only a test can do because only a test already knows which
    workspace it is looking for.
    """
    claimed = (await db.execute(text(CLAIM_SQL), {"stale": STALE_AFTER_MINUTES})).first()
    if claimed is None:
        return None
    await db.commit()

    run_id, workspace_id = claimed.id, claimed.workspace_id
    await apply_workspace_scope(db, workspace_id)

    row = (
        await db.execute(
            text("SELECT domain, website_url FROM workspace WHERE id = :w"),
            {"w": str(workspace_id)},
        )
    ).first()
    seeds = [
        u
        for u in ((row.website_url if row else None), (f"https://{row.domain}" if row else None))
        if u
    ]

    # **Commit before fanning out.** This session opened a transaction to read
    # the workspace, and a transaction held open across the gather keeps a
    # snapshot from before any source committed — so the read below would find
    # every source still `running` and derive a state from stale rows. Nothing
    # errors; the run simply never appears to finish.
    await db.commit()

    limit = asyncio.Semaphore(CONCURRENT_SOURCES)

    async def guarded(kind: SourceKind) -> None:
        # **Its own session.** An `AsyncSession` is not safe to use from several
        # tasks at once — asyncpg raises on the concurrent use, `gather` with
        # `return_exceptions=True` swallows it, and every source is left sitting
        # at `running` forever with nothing in the log. Found exactly that way.
        async with limit, get_sessionmaker()() as own:
            await _run_source(own, workspace_id=workspace_id, run_id=run_id, kind=kind, seeds=seeds)

    # `gather` without `return_exceptions` would cancel the siblings of the
    # first source to raise — the precise opposite of Q56. `_run_source` does
    # not raise, and this says so a second time rather than relying on it.
    await asyncio.gather(*(guarded(k) for k in SourceKind), return_exceptions=True)

    await apply_workspace_scope(db, workspace_id)
    states = [
        SourceState(r.state)
        for r in (
            await db.execute(
                text("SELECT state FROM research_source WHERE run_id = :r"),
                {"r": str(run_id)},
            )
        ).all()
    ]
    await db.execute(
        text("UPDATE research_run SET state = :s, finished_at = now() WHERE id = :i"),
        {"s": state_for(states).value, "i": str(run_id)},
    )
    await db.commit()

    log.info("research.run_finished", run_id=str(run_id), state=state_for(states).value)
    return UUID(str(run_id))
