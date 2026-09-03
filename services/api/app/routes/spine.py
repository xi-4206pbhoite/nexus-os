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
from sqlalchemy import text

from app.auth.csrf import require_csrf
from app.db import _unscoped_session
from app.deps import CurrentScope
from app.domain import audit
from app.domain.department_answers import (
    AnswerState,
    may_answer_department_question,
    state_for_answer,
)
from app.domain.departments import (
    RECOMMENDED_MAX,
    RECOMMENDED_MIN,
    SELECTABLE,
    select_departments,
    selected_departments,
)
from app.domain.onboarding import BY_KEY, COMPANY_QUESTIONS, resolve_answer
from app.domain.progress import STAGES, complete_stage, progress_for
from app.domain.question_bank import BY_DEPARTMENT
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


# ── Department blocks (P7) ────────────────────────────────────


class BlockQuestionOut(BaseModel):
    key: str
    prompt: str
    why: str
    answer_type: str
    consumed_by: str
    answered: bool
    proposed: bool


class BlockOut(BaseModel):
    department: str
    may_answer: bool
    binds: bool
    questions: list[BlockQuestionOut]


@router.get("/departments/{department}/block", response_model=BlockOut)
async def read_department_block(department: str, scope: CurrentScope) -> BlockOut:
    """One department's questions, and whether this caller may answer them.

    `may_answer` and `binds` are returned rather than left for the client to
    infer. A UI deciding for itself would be guessing at an authority rule, and
    the guesses that matter are the wrong ones — a Contributor shown a form that
    binds, or a Manager shown a read-only block for their own department.

    Served to callers who **may not** answer it, with `may_answer: false`.
    Hiding it would leave a Contributor unable to see what their own department
    has been asked, which is information they are entitled to and which the
    stored answers already carry.
    """
    try:
        target = Department(department)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such department.") from exc

    questions = BY_DEPARTMENT.get(target, ())
    if not questions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No block for that department.")

    async with scoped_connection(scope) as db:
        rows = {
            r.question_key: r.answer_state
            for r in (
                await db.execute(
                    text(
                        "SELECT question_key, answer_state FROM onboarding_answer"
                        " WHERE department = :d"
                    ),
                    {"d": target.value},
                )
            ).all()
        }

    return BlockOut(
        department=target.value,
        may_answer=may_answer_department_question(
            role=scope.role, caller_departments=scope.departments, department=target
        ),
        binds=state_for_answer(role=scope.role, caller_departments=scope.departments)
        is AnswerState.BOUND,
        questions=[
            BlockQuestionOut(
                key=q.key,
                prompt=q.prompt,
                why=q.why,
                answer_type=q.answer_type.value,
                consumed_by=q.consumed_by,
                answered=q.key in rows,
                proposed=rows.get(q.key) == AnswerState.PROPOSED.value,
            )
            for q in questions
        ],
    )


class BlockAnswer(BaseModel):
    key: str
    value: str = Field(max_length=4000)


class BlockAnswersIn(BaseModel):
    answers: list[BlockAnswer]


@router.post(
    "/departments/{department}/block",
    response_model=BlockOut,
    dependencies=[Depends(require_csrf)],
)
async def answer_department_block(
    department: str, payload: BlockAnswersIn, scope: CurrentScope
) -> BlockOut:
    """Answer a department's questions.

    Two checks, and they are not the same check (Q30, Q31). **May you answer at
    all** depends on which department this is — a Sales Manager may not
    configure Finance. **Does your answer bind** depends on your role alone — a
    Contributor's is proposed and waits for the review gate.

    A Contributor reaches this route legitimately, because proposing *is*
    answering. So the check permits them for their own department and
    `state_for_answer` decides what the row means, rather than the route
    refusing and the product losing a proposal it asked for.
    """
    try:
        target = Department(department)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such department.") from exc

    binding = state_for_answer(role=scope.role, caller_departments=scope.departments)

    permitted = may_answer_department_question(
        role=scope.role, caller_departments=scope.departments, department=target
    ) or (binding is AnswerState.PROPOSED and target in scope.departments)

    if not permitted:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"You cannot answer the {target.value} questions. A department's "
            "questions are answered by its manager, or by an owner.",
        )

    bank = {q.key: q for q in BY_DEPARTMENT.get(target, ())}
    unknown = [a.key for a in payload.answers if a.key not in bank]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Not questions in this block: {sorted(unknown)}"
        )

    async with scoped_connection(scope) as db:
        for answer in payload.answers:
            await store_answer(
                db,
                caller=scope,
                question=bank[answer.key],
                value=answer.value,
                answer_state=binding.value,
            )

    log.info(
        "onboarding.block.answered",
        department=target.value,
        binding=binding.value,
        count=len(payload.answers),
    )
    return await read_department_block(target.value, scope)
