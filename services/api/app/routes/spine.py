"""The onboarding spine, over HTTP.

`doc/12` §Phase 6. Three things the single-page wizard had no way to express:
where a founder is, what they have finished, and which departments they run.

**Progress is read and written server-side.** The client asks where it should be
rather than deciding — otherwise a stale tab, a Back button or a second device
each hold their own opinion, and the one that writes last wins. There is one
answer and the database holds it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.csrf import require_csrf
from app.db import _unscoped_session
from app.deps import CurrentScope
from app.domain import audit
from app.domain.departments import (
    RECOMMENDED_MAX,
    RECOMMENDED_MIN,
    SELECTABLE,
    select_departments,
    selected_departments,
)
from app.domain.onboarding import BY_KEY, COMPANY_QUESTIONS, resolve_answer
from app.domain.progress import STAGES, complete_stage, progress_for
from app.domain.scopes import Department
from app.logging import get_logger
from app.retrieval.scoped import scoped_connection
from app.routes.setup import store_answer

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
log = get_logger(__name__)


class StageOut(BaseModel):
    current: str
    completed: list[str]
    stages: list[str]
    finished: bool


class CompanyQuestionOut(BaseModel):
    key: str
    prompt: str
    why: str
    required: bool
    assumption_when_unsure: str | None


class DepartmentOut(BaseModel):
    value: str
    selected: bool


class SpineOut(BaseModel):
    """Everything the flow needs to render itself, in one call.

    One request rather than three, because a stage rail that renders before it
    knows which stages are done shows the wrong one and then corrects itself,
    and a founder reads that as the product losing their place.
    """

    stage: StageOut
    company_questions: list[CompanyQuestionOut]
    departments: list[DepartmentOut]
    recommended: dict[str, int]


@router.get("/state", response_model=SpineOut)
async def read_state(scope: CurrentScope) -> SpineOut:
    async with _unscoped_session() as db:
        progress = await progress_for(db, workspace_id=scope.workspace_id)
        chosen = await selected_departments(db, workspace_id=scope.workspace_id)

    return SpineOut(
        stage=StageOut(
            current=progress.current,
            completed=sorted(progress.completed),
            stages=list(STAGES),
            finished=progress.finished,
        ),
        company_questions=[
            CompanyQuestionOut(
                key=q.key,
                prompt=q.prompt,
                why=q.why,
                required=q.required,
                assumption_when_unsure=q.assumption_when_unsure,
            )
            for q in COMPANY_QUESTIONS
        ],
        # `SELECTABLE` excludes the Chief of Staff, which is automatic (Q24) and
        # must never appear as a checkbox somebody can clear.
        departments=[DepartmentOut(value=d.value, selected=d in chosen) for d in SELECTABLE],
        recommended={"min": RECOMMENDED_MIN, "max": RECOMMENDED_MAX},
    )


class CompanyAnswer(BaseModel):
    key: str
    value: str | None = Field(default=None, max_length=4000)
    unsure: bool = False


class CompanyAnswersIn(BaseModel):
    answers: list[CompanyAnswer]


@router.post("/company", response_model=StageOut, dependencies=[Depends(require_csrf)])
async def save_company_stage(payload: CompanyAnswersIn, scope: CurrentScope) -> StageOut:
    """Store the five company answers and advance.

    Every answer goes through `resolve_answer`, so **"not sure yet" can never
    store a null** — it stores the question's stated assumption instead, flagged
    as one. A null would be indistinguishable from a question nobody reached,
    and those two want different behaviour everywhere downstream.
    """
    unknown = [a.key for a in payload.answers if a.key not in BY_KEY]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown question keys: {sorted(unknown)}"
        )

    # Stored through the same `store_answer` the wizard uses, so scope tagging
    # at capture (doc 06 §2.5) still happens in exactly one place — and through
    # `resolve_answer`, so "not sure yet" becomes a flagged assumption rather
    # than a null.
    async with scoped_connection(scope) as session:
        for answer in payload.answers:
            question = BY_KEY[answer.key]
            resolved = resolve_answer(question, value=answer.value, unsure=answer.unsure)
            await store_answer(
                session,
                caller=scope,
                question=question,
                value=resolved.value,
                is_assumption=resolved.is_assumption,
            )

    async with _unscoped_session() as db:
        progress = await complete_stage(db, workspace_id=scope.workspace_id, stage="company")
        await audit.record(
            db,
            workspace_id=scope.workspace_id,
            action=audit.AuditAction.ANSWER_WRITTEN,
            actor_user_id=scope.user_id,
            target_type="onboarding_stage",
            target_id="company",
            reason=f"{len(payload.answers)} answers",
        )
        await db.commit()

    return StageOut(
        current=progress.current,
        completed=sorted(progress.completed),
        stages=list(STAGES),
        finished=progress.finished,
    )


class DepartmentsIn(BaseModel):
    departments: list[str]


@router.post("/departments", response_model=StageOut, dependencies=[Depends(require_csrf)])
async def save_departments(payload: DepartmentsIn, scope: CurrentScope) -> StageOut:
    """Select the departments, and advance.

    No minimum is enforced. Q23 recommends three to five; a company that runs
    two functions should be able to say two, and refusing that would make the
    product's tidiness more important than the customer's reality.
    """
    try:
        chosen = {Department(d) for d in payload.departments}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown department.") from exc

    async with _unscoped_session() as db:
        await select_departments(db, workspace_id=scope.workspace_id, departments=chosen)
        progress = await complete_stage(db, workspace_id=scope.workspace_id, stage="departments")
        await db.commit()

    log.info("onboarding.departments.selected", count=len(chosen))
    return StageOut(
        current=progress.current,
        completed=sorted(progress.completed),
        stages=list(STAGES),
        finished=progress.finished,
    )
