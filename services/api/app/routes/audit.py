"""Reading the audit trail.

Doc 07 I9. The log answers "who did what, to what, and when" for one workspace,
and the answer is only useful if it is also **restricted** — a trail every member
can read tells each of them who else signed in, who was invited, and who uploaded
what, which is a surveillance surface rather than an accountability one.

Owner and Executive, via `require_executive_surface`, which already encodes
exactly that pair for doc 06 §2.4's reasons. Reusing it rather than writing a
second role check is deliberate: two places that decide who is senior enough will
eventually disagree, and the one nobody updated will be the one guarding
something.

**Read through `scoped_connection`.** The isolation policy on `audit_log` is what
actually confines the result to one workspace; the role check above decides
whether the caller may see their *own* workspace's log at all. Both, and in that
order — a role check over an unscoped query would happily show an Owner every
other company's trail.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.deps import require_executive_surface
from app.domain.session import ScopedSession
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/audit-log", tags=["audit"])

ExecutiveScope = Annotated[ScopedSession, Depends(require_executive_surface)]


class AuditEntry(BaseModel):
    action: str
    actor_user_id: UUID | None
    target_type: str | None
    target_id: str | None
    reason: str | None
    at: datetime


class AuditPage(BaseModel):
    entries: list[AuditEntry]


@router.get("", response_model=AuditPage)
async def read_audit_log(
    scope: ExecutiveScope,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    """The workspace's own trail, newest first.

    Bounded by `limit` with a ceiling rather than offering everything: an
    unbounded read of a table that grows with every action in the product is a
    denial-of-service against ourselves, and 200 is more than a human reads.
    Paging by cursor arrives when something needs it — an offset here would be
    wrong anyway, because rows are inserted while a reader pages.
    """
    async with scoped_connection(scope) as db:
        rows = (
            await db.execute(
                text(
                    "SELECT action, actor_user_id, target_type, target_id, reason, at"
                    "  FROM audit_log ORDER BY at DESC LIMIT :n"
                ),
                {"n": limit},
            )
        ).all()

    return AuditPage(
        entries=[
            AuditEntry(
                action=r.action,
                actor_user_id=UUID(str(r.actor_user_id)) if r.actor_user_id else None,
                target_type=r.target_type,
                target_id=r.target_id,
                reason=r.reason,
                at=r.at,
            )
            for r in rows
        ]
    )
