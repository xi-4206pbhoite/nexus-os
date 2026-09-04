"""Research progress. **Never one spinner** (Q57).

A run fans out across six independent sources, and a single spinner over the top
of them is a lie of omission: it says "working" while the crawl has already
failed, the connector was skipped, and only keywords are still going. The
founder cannot tell whether to wait, to fix something, or to walk away.

So this returns **every source with its own outcome**, including the ones that
failed and why. A screen built on it can say "your website could not be read —
it renders with JavaScript; we will use your answers and documents instead"
while three other sources are still running.

The run's own state is derived from the sources (`state_for`) rather than read
from the row, so the two can never disagree on screen — which they would the
moment a worker updated one and crashed before the other.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.deps import CurrentScope
from app.domain.research import SourceState, state_for
from app.logging import get_logger
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/research", tags=["research"])
log = get_logger(__name__)


class SourceOut(BaseModel):
    kind: str
    state: str
    error_reason: str
    """Empty unless this source failed. Never empty when it did — the schema
    enforces both halves, so a screen can trust it without checking."""

    started_at: object | None = None
    finished_at: object | None = None


class RunOut(BaseModel):
    run_id: UUID
    state: str
    """Derived from the sources, not read from the row. The two cannot disagree
    on screen — which they would the moment a worker updated one and crashed
    before the other."""

    sources: list[SourceOut]
    still_running: int
    """So a caller can decide whether to poll again without re-deriving the
    rule. One number, one meaning."""


@router.get("/{run_id}", response_model=RunOut)
async def read_run(run_id: UUID, scope: CurrentScope) -> RunOut:
    """One run's progress, source by source.

    Scoped by RLS: a run id from another workspace is a 404 rather than a 403,
    because "that run exists and is not yours" confirms another company is using
    the product and roughly when.
    """
    async with scoped_connection(scope) as db:
        run = (
            await db.execute(text("SELECT id FROM research_run WHERE id = :i"), {"i": str(run_id)})
        ).first()
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such research run.")

        rows = (
            await db.execute(
                text(
                    "SELECT kind, state, error_reason, started_at, finished_at"
                    "  FROM research_source WHERE run_id = :i ORDER BY kind"
                ),
                {"i": str(run_id)},
            )
        ).all()

    sources = [
        SourceOut(
            kind=row.kind,
            state=row.state,
            error_reason=row.error_reason,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        for row in rows
    ]
    states = [SourceState(row.state) for row in rows]

    return RunOut(
        run_id=run_id,
        state=state_for(states).value,
        sources=sources,
        still_running=sum(1 for s in states if s in (SourceState.QUEUED, SourceState.RUNNING)),
    )
