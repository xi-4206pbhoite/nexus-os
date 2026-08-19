"""Workspace setup: the onboarding answers, and the people invited to help.

Distinct from `routes/onboarding.py`, which is everything that happens *before*
a workspace exists — verify an email, prove a domain, create the workspace. From
here on there is a workspace, so every route in this module takes a
`ScopedSession` and every read goes through `scoped_connection`. The one
exception is invitation acceptance, and it is exactly the case that proves the
rule: the person accepting is not yet a member, so no scope can honestly be
built for them.

Two properties are worth reading the code for, because both are the kind that
quietly stop being true:

**Scope is taken from the catalogue, never from the request.** `AnswerIn` has a
`key` and a `value` and no third field. There is no scope to spoof, because the
classification is looked up in `scope_for_answer` — which raises on an unknown
key rather than defaulting (doc 06 §2.5, I4). A request cannot store its average
deal size as L1 by asking nicely.

**Answering is not authorising.** The `role` and `department` questions write
rows in `onboarding_answer`. Nothing here touches `membership`, which is the
only table `build_scope` reads. Doc 06 §2.2 calls a self-declared role privilege
escalation via dropdown; the reason it cannot happen is not that this module is
careful, but that the write it would need is not in this file at all.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.persona import (
    CommunicationStyle,
    LandingScreen,
    propose_persona,
)
from app.ai.contracts import LlmProvider
from app.ai.registry import get_provider
from app.auth import invitations as invites
from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.connectors.crawler import FetchError, fetch_page
from app.connectors.extract import extract_signals
from app.db import _unscoped_session
from app.deps import CurrentScope, CurrentSession
from app.domain.access import AccessDecision, Aggregate, decide_l3_access
from app.domain.dashboards import (
    CONNECTABLE,
    DIRECTORS,
    landing_department,
    offerings_needing,
)
from app.domain.invitations import InvitationError, check_invitation, may_administer
from app.domain.onboarding import (
    BY_KEY,
    CATALOGUE,
    TOOL_LABELS,
    AnswerType,
    Choice,
    Question,
    Sink,
    scope_for_answer,
)
from app.domain.scopes import Department, Role, Scope, scope_code, scope_from_code
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.mail import Email, FileMailer, Mailer
from app.retrieval.scoped import scoped_connection

router = APIRouter(tags=["setup"])
log = get_logger(__name__)

MAX_TEXT = 300
MAX_LONG_TEXT = 4000
MAX_URL = 2048
MAX_LIST_ITEMS = 25
MAX_ITEM_LENGTH = 120


# ── Reading and writing one answer's authority ────────────────


def may_read_answer(caller: ScopedSession, scope: Scope, department: Department | None) -> bool:
    """Whether this caller may see an answer stored at this classification.

    An L3 answer is a department-wide fact — the department's average deal size,
    not one person's — so it is decided as an aggregate. That is what withholds
    it from a Contributor, per ADR 0005, and it is the same call the dashboards
    will make about the same number when they compute with it.
    """
    if scope is Scope.L3_DEPARTMENT:
        if department is None:
            # Unclassifiable: a CHECK constraint forbids storing this, so
            # reaching it means the row predates the constraint or arrived some
            # other way. Withhold rather than guess (I4).
            return False
        aggregate = Aggregate("onboarding_answer", department)
        return decide_l3_access(caller, aggregate=aggregate) is AccessDecision.ALLOW
    return caller.may_reach_scope(scope)


def departments_selected(answers: dict[str, Any]) -> frozenset[Department]:
    """Which department blocks this company runs, from its own answer (doc 08 §1.6).

    Unrecognised values are dropped rather than raising. The stored answer is
    validated against the catalogue's options on the way in, so a value that is not
    a `Department` means the enum changed under an existing row — and the honest
    response to that is to stop offering the block, not to fail the whole wizard.
    """
    raw = answers.get("departments_run") or []
    if not isinstance(raw, list):
        return frozenset()

    selected: set[Department] = set()
    for value in raw:
        try:
            selected.add(Department(value))
        except ValueError:
            continue
    return frozenset(selected)


def may_be_asked(
    caller: ScopedSession, question: Question, selected: frozenset[Department]
) -> bool:
    """Whether this question belongs in this caller's wizard at all.

    Two independent narrowings, and they are not the same thing:

    - **The company runs it.** An unselected department's questions are absent, not
      disabled — doc 08 §2.2's principle applied to the form: a channel that is not
      run is reported as *not run*, never as zero, and a department the company does
      not have should not be a row of greyed-out inputs implying it forgot something.
    - **The caller reaches it.** Doc 08 §0: *"An invited team member answers only
      their own department's set — a Sales Executive is never asked when the financial
      year ends."* `may_reach_department` is the same call the dashboards make, so a
      Sales manager cannot be handed Finance's questions here either.

    Company-wide questions have no `asked_of` and are unaffected.
    """
    if question.asked_of is None:
        return True
    return question.asked_of in selected and caller.may_reach_department(question.asked_of)


async def _stored_selection(session: AsyncSession) -> frozenset[Department]:
    """The company's current `departments_run`, straight from its own row."""
    row = (
        await session.execute(
            text("SELECT value FROM onboarding_answer WHERE question_key = 'departments_run'")
        )
    ).first()
    return departments_selected({"departments_run": row.value if row else None})


def _selection_after(
    batch: dict[Question, Any], stored: frozenset[Department]
) -> frozenset[Department]:
    """The selection this request leaves behind.

    If the batch sets `departments_run`, that value decides — a client may
    legitimately select a department and answer its questions in one request, and
    judging that batch against the *previous* selection would refuse the second half
    of a perfectly coherent submission.
    """
    for question, value in batch.items():
        if question.key == "departments_run":
            return departments_selected({"departments_run": value})
    return stored


def ensure_may_answer(caller: ScopedSession, question: Question) -> None:
    """Refuse an answer this caller has no business setting.

    Two layers, and the second is not currently reachable past the first.

    The first is `may_administer`: the catalogue is a *company* setup flow run
    once by the founder, so writing to it is workspace administration. No source
    document says who may run it — D16 — so this is the default-deny reading.

    The second is the per-answer check. It is redundant while only Owner and
    Executive get past the first, and it is written and tested anyway: if D16
    later admits Department Managers, this is what stops one from writing an
    L3 Finance fact from a Sales seat. D15's second open question is precisely
    that failure, and a check added at the same time as the feature that needs
    it is a check nobody remembers to add.
    """
    if not may_administer(caller.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Workspace setup is available to owners and executives.",
        )

    if not may_read_answer(caller, question.scope, question.department):
        # 404 rather than 403: for an L3 department the caller cannot reach,
        # confirming the question exists confirms the department does.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    # The routing check, which `may_read_answer` above cannot make: doc 08 §3.1's
    # pipeline stages are classified **L2**, so every role that can see the company
    # can read them — but a Finance manager still has no business defining Sales's
    # pipeline. D15's second open question is exactly this, and it is only reachable
    # once D16 admits anyone below Executive; written now because a check added
    # alongside the feature that needs it is a check nobody remembers to add.
    if question.asked_of is not None and not caller.may_reach_department(question.asked_of):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


# ── Value validation ──────────────────────────────────────────


def _text(value: Any, *, limit: int, label: str) -> str:
    if not isinstance(value, str):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be text.")
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} cannot be empty.")
    if len(cleaned) > limit:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{label} is longer than {limit} characters."
        )
    return cleaned


def _string_list(value: Any, *, options: tuple[Choice, ...], label: str) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be a list.")
    if len(value) > MAX_LIST_ITEMS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{label} takes at most {MAX_LIST_ITEMS} entries."
        )

    permitted = {c.value for c in options}
    cleaned: list[str] = []
    for item in value:
        entry = _text(item, limit=MAX_ITEM_LENGTH, label=label)
        if permitted and entry not in permitted:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{entry!r} is not an option.")
        if entry not in cleaned:  # order-preserving dedupe; RANKED depends on order
            cleaned.append(entry)
    return cleaned


NOT_A_WEB_ADDRESS = "That does not look like a web address."

HOSTNAME = re.compile(
    r"^(?=.{1,253}$)"
    r"(?!-)[a-z0-9-]{1,63}(?<!-)"
    r"(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
)
"""A dotted host, and nothing else.

Written out rather than leaning on `urlparse` alone, which is permissive by
design: it happily reports a hostname for `not a url` and for
`javascript:alert(1)`, both of which reached the database before this existed.
A single missing dot is the difference between a company's site and a scheme
somebody typed to see what would happen.
"""


def _web_address(raw: str) -> str:
    """A stored company URL, or a 400.

    A bare host is accepted and given `https://`, because that is how people
    type their own address. Anything with a scheme must carry one we would
    actually fetch — this value feeds the crawler, so `file:` and `javascript:`
    are not merely untidy.
    """
    if "://" in raw:
        scheme = raw.split("://", 1)[0].lower()
        if scheme not in ("http", "https"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS)
        candidate = raw
    elif ":" in raw.split("/", 1)[0]:
        # `javascript:alert(1)` has a scheme and no `//`. Prefixing `https://`
        # would turn it into a host called `javascript` with a port that is not
        # a number, which is a strange thing to have stored.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS)
    else:
        candidate = f"https://{raw}"

    parsed = urlparse(candidate)
    try:
        _ = parsed.port  # raises when the port is not a number
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS) from exc

    host = (parsed.hostname or "").lower()
    if not HOSTNAME.match(host):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_A_WEB_ADDRESS)

    return parsed.geturl()


def validate_answer(question: Question, value: Any, *, member_ids: frozenset[UUID]) -> Any:
    """The stored form of an answer, or a 400.

    Returns the value to write rather than mutating anything, so the caller can
    validate a whole submission before writing any of it.
    """
    label = question.prompt

    match question.answer_type:
        case AnswerType.TEXT:
            return _text(value, limit=MAX_TEXT, label=label)

        case AnswerType.LONG_TEXT:
            return _text(value, limit=MAX_LONG_TEXT, label=label)

        case AnswerType.URL:
            return _web_address(_text(value, limit=MAX_URL, label=label))

        case AnswerType.MONEY:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be a number.")
            if value != value or value in (float("inf"), float("-inf")):  # NaN, ±inf
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label} must be a number.")
            if value < 0:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"{label} cannot be a negative number."
                )
            return float(value)

        case AnswerType.SINGLE_CHOICE:
            chosen = _text(value, limit=MAX_ITEM_LENGTH, label=label)
            if chosen not in {c.value for c in question.options}:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{chosen!r} is not an option.")
            return chosen

        case AnswerType.MULTI_CHOICE | AnswerType.RANKED:
            return _string_list(value, options=question.options, label=label)

        case AnswerType.USER_LIST:
            recipients: list[str] = []
            for entry in _string_list(value, options=(), label=label):
                try:
                    user_id = UUID(entry)
                except ValueError as exc:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, "Choose people from your workspace."
                    ) from exc
                if user_id not in member_ids:
                    # Doc 06 §4.10 — the brief goes to workspace users, never to
                    # a free-text address. The route is where that stops being a
                    # sentence in a document.
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        "Everyone on this list has to be in your workspace already.",
                    )
                recipients.append(str(user_id))
            return recipients


# ── Wire models ───────────────────────────────────────────────


class ChoiceOut(BaseModel):
    value: str
    label: str


class QuestionOut(BaseModel):
    key: str
    prompt: str
    stage: str
    answer_type: str
    scope: str
    department: str | None
    asked_of: str | None = None
    """Whose block this question belongs to, so the client can group the stage.

    Distinct from `department`, which is the scope classification — see
    `Question.asked_of`. Only ever set on department-block questions.
    """
    required: bool
    why: str
    options: list[ChoiceOut]
    free_entry: bool
    writable: bool
    """Whether this caller may set it. False renders read-only, not hidden —
    a question the caller can see the answer to but not change is a real state."""
    value: Any = None
    """The stored answer, when this caller may read it. `None` otherwise, with
    no indication of which of the two it was."""


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None
    role: str


class QuestionsOut(BaseModel):
    questions: list[QuestionOut]
    can_administer: bool
    members: list[MemberOut]
    """Empty unless the caller administers the workspace. The brief-recipient
    question is chosen from this list and from nowhere else."""


class AnswerIn(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: Any
    # No scope field, and there never may be one. See the module docstring.


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=len(CATALOGUE))


class SavedOut(BaseModel):
    saved: list[str]


# ── Members ───────────────────────────────────────────────────


async def _members(session: AsyncSession) -> list[MemberOut]:
    """The workspace's people.

    Filtered to the workspace by the isolation policy on `membership`, not by
    this query. `app_user` is global and carries no policy of its own, so the
    join is the reason a caller sees only their colleagues' rows.
    """
    rows = (
        (
            await session.execute(
                text(
                    "SELECT m.user_id, u.email, u.display_name, m.role"
                    "  FROM membership m JOIN app_user u ON u.id = m.user_id"
                    " WHERE m.revoked_at IS NULL"
                    " ORDER BY lower(u.email)"
                )
            )
        )
        .mappings()
        .all()
    )
    return [
        MemberOut(
            user_id=UUID(str(r["user_id"])),
            email=r["email"],
            display_name=r["display_name"],
            role=r["role"],
        )
        for r in rows
    ]


async def store_answer(
    session: AsyncSession, *, caller: ScopedSession, question: Question, value: Any
) -> None:
    """Write one answer, classified from the catalogue.

    The scope and department are looked up here, from `scope_for_answer`, and
    the caller passes neither. That is doc 06 §2.5's *"tag them at capture"* in
    one function: there is no argument to get wrong and no request field to
    trust, and a question the catalogue does not know raises rather than
    defaulting to a scope somebody guessed.

    An upsert, because onboarding is revisitable — a person correcting their
    currency in week three is the ordinary case, not a conflict. The
    classification is re-applied on update as well as insert: a question that is
    reclassified upward must not leave old rows sitting at the weaker scope
    forever because they happened to be answered first.

    A question whose `sink` is not `ANSWER` goes to its real column instead, and
    **only** there — see `Sink`. Writing both would give one fact two homes that
    can disagree.
    """
    if question.sink is Sink.WORKSPACE_NAME:
        # RLS scopes this to the caller's own workspace: the policy's USING clause
        # compares `workspace_id` to the GUC `scoped_connection` set, so there is no
        # workspace id in this statement to point at somebody else's row.
        await session.execute(
            text("UPDATE workspace SET name = :n WHERE id = :ws"),
            {"n": str(value).strip(), "ws": str(caller.workspace_id)},
        )
        return

    if question.sink is Sink.USER_DISPLAY_NAME:
        # `app_user` carries no workspace column and therefore no RLS, so the
        # predicate is the whole protection here. It is the session's user id (I2),
        # never a value from the request — there is no request field that could
        # aim this at another account.
        await session.execute(
            text("UPDATE app_user SET display_name = :n WHERE id = :u"),
            {"n": str(value).strip(), "u": str(caller.user_id)},
        )
        return

    answer_scope, department = scope_for_answer(question.key)

    await session.execute(
        text(
            "INSERT INTO onboarding_answer"
            " (workspace_id, answered_by_user_id, question_key, value, scope, department)"
            " VALUES (:ws, :u, :k, CAST(:v AS jsonb), :s, :d)"
            " ON CONFLICT (workspace_id, question_key) DO UPDATE"
            "    SET value = EXCLUDED.value,"
            "        scope = EXCLUDED.scope,"
            "        department = EXCLUDED.department,"
            "        answered_by_user_id = EXCLUDED.answered_by_user_id,"
            "        updated_at = now()"
        ),
        {
            "ws": str(caller.workspace_id),
            "u": str(caller.user_id),
            "k": question.key,
            "v": json.dumps(value),
            "s": scope_code(answer_scope),
            "d": department.value if department else None,
        },
    )


# ── The catalogue, with this caller's answers ─────────────────


class CompletionOut(BaseModel):
    completed_at: datetime
    landing_department: str | None
    """Where to send them. `None` when their membership names no department — there
    is no sensible default, and inventing one puts somebody in a department nobody
    assigned them to."""

    email_sent: bool
    email_detail: str
    """Why not, when `email_sent` is false. Completion never depends on it."""

    already_complete: bool
    """True when this call changed nothing. A second click must not re-send."""


def _mailer(settings: Settings) -> Mailer | None:
    """The configured mailer, or `None` when there is not one.

    `None` rather than an exception: a missing mailer must never block completion.
    That is this phase's stated requirement and it is also the right default — the
    account exists, the setup is finished, and refusing to record that because a
    notification could not go out would lose the thing that matters to keep the thing
    that does not.
    """
    if settings.mailer_backend == "file":
        return FileMailer(settings.mail_root)
    return None


MISSING_ANSWER_LIMIT = 10


@router.post(
    "/onboarding/complete",
    response_model=CompletionOut,
    dependencies=[Depends(require_csrf)],
)
async def complete_setup(
    scope: CurrentScope,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CompletionOut:
    """Mark setup finished, tell the user, and say where to go next.

    **Idempotent, and it has to be.** The timestamp is set with
    `WHERE setup_completed_at IS NULL ... RETURNING`, so the database decides whether
    this call was the transition. A read-then-write would let two clicks both see
    `NULL` and both send an email — the classic version of this bug, and the reason
    the check and the write are one statement.

    **Required answers are enforced here rather than only in the UI.** `required` had
    been a rendering hint; completing without `company_url` would have marked a
    workspace set up while the audit had nothing to read. The response names what is
    missing, because a refusal that does not say what to fix is a dead end.

    **Email never gates completion.** It is sent after the transition and its failure
    is reported in the payload, not raised. Doc 07's honesty rule cuts both ways: the
    user is told the notification did not go out, and is not blocked by it.
    """
    async with scoped_connection(scope) as session:
        answered = {
            row.question_key
            for row in await session.execute(text("SELECT question_key FROM onboarding_answer"))
        }
        selected = await _stored_selection(session)

        # Prompts, not keys. This string is shown to the user, and it read
        # "Still needed: company_url, departments_run, fiscal_year_start" — three
        # column names for a person who has only ever seen "Your website address".
        # The prompt is the only version of a question they can act on.
        missing = [
            question.prompt
            for question in CATALOGUE
            if question.required
            and question.sink is Sink.ANSWER
            and may_be_asked(scope, question, selected)
            and question.key not in answered
        ]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Still needed before setup can be marked complete: "
                + ", ".join(missing[:MISSING_ANSWER_LIMIT]),
            )

        # One statement: the WHERE clause is what makes this idempotent, and
        # RETURNING is what tells us whether we were the ones who changed it.
        row = (
            await session.execute(
                text(
                    "UPDATE workspace SET setup_completed_at = now()"
                    " WHERE id = :ws AND setup_completed_at IS NULL"
                    " RETURNING setup_completed_at"
                ),
                {"ws": str(scope.workspace_id)},
            )
        ).first()

        transitioned = row is not None

        # The workspace name and the caller's own address, in one statement. The
        # address is joined on the *session's* user id, never one from the request —
        # this is the only place a recipient is chosen, so there is one thing to read
        # when asking "could this ever email somebody else?".
        details = (
            await session.execute(
                text(
                    "SELECT w.name, w.setup_completed_at, u.email"
                    "  FROM workspace w, app_user u"
                    " WHERE w.id = :ws AND u.id = :u"
                ),
                {"ws": str(scope.workspace_id), "u": str(scope.user_id)},
            )
        ).one()
        completed_at = details.setup_completed_at
        workspace_name = details.name
        recipient = details.email

    landing = landing_department(
        executive_surface=scope.can_see_executive_surface,
        departments=scope.departments,
    )

    sent, detail = (
        _notify_setup_complete(settings, recipient=recipient, workspace_name=workspace_name)
        if transitioned
        else (False, "Already complete — no second notification is sent.")
    )

    log.info(
        "onboarding.completed",
        transitioned=transitioned,
        email_sent=sent,
        landing=landing.value if landing else None,
    )
    return CompletionOut(
        completed_at=completed_at,
        landing_department=landing.value if landing else None,
        email_sent=sent,
        email_detail=detail,
        already_complete=not transitioned,
    )


def _notify_setup_complete(
    settings: Settings, *, recipient: str | None, workspace_name: str
) -> tuple[bool, str]:
    """Best effort, and honest about it. Never raises.

    The recipient is passed in, already read from `app_user` on the session's user id.
    Doc 06 §4.10's rule — that output goes to workspace users, resolved at send time —
    starts here even though this is one transactional message rather than a brief.
    """
    mailer = _mailer(settings)
    if mailer is None:
        return False, (
            f"No mailer is configured ({settings.mailer_backend!r}), so no email was "
            "sent. Your setup is complete regardless."
        )
    if not recipient:
        return False, "No address on file for your account, so no email was sent."

    try:
        mailer.send(
            Email(
                to=recipient,
                subject=f"{workspace_name} is set up on NEXUS OS",
                text_body=(
                    f"Your workspace {workspace_name} is set up.\n\n"
                    "What exists now: your company details, the departments you run and "
                    "their questions, and your profile.\n\n"
                    "What does not: every dashboard capability is still unbuilt, and no "
                    "tool is connected. Each tile says so rather than showing a zero.\n"
                ),
            )
        )
    except OSError as exc:
        # Type only — a mail path can carry the deployment layout.
        log.warning("onboarding.complete.mail_failed", error=type(exc).__name__)
        return False, "The notification could not be sent. Your setup is complete regardless."

    return True, ""


class PersonaProposalOut(BaseModel):
    summary: str
    priority_topics: list[str]
    communication_style: str | None
    default_landing_screen: str | None
    available: bool
    unavailable_reason: str
    provenance: list[str]
    """What was read to produce this. Stands in for the `generation` row M8 will add."""


class PersonaIn(BaseModel):
    """What a human confirmed. Deliberately *not* the proposal object.

    A confirm endpoint that accepted "the proposal I just showed you" would be
    trusting a value the client could not have edited meaningfully. These are the
    fields as the person left them, validated here, so an edited proposal and a
    hand-written persona take exactly the same path.
    """

    stated_purpose: str | None = Field(default=None, max_length=MAX_LONG_TEXT)
    priority_topics: list[str] = Field(default_factory=list)
    communication_style: str | None = None
    default_landing_screen: str | None = None
    language: str = Field(default="en", max_length=8)
    timezone: str = Field(default="Asia/Muscat", max_length=64)


@router.post("/onboarding/persona/propose", response_model=PersonaProposalOut)
async def propose_persona_route(
    scope: CurrentScope,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[LlmProvider, Depends(get_provider)],
) -> PersonaProposalOut:
    """Run the agent team and return a proposal. **Writes nothing.**

    Two agents: company research over a page fetched from the workspace's own domain,
    and profile analysis over the answers the user typed. Neither touches a document,
    a chunk or a vector search, which is what keeps this off M6.

    Nothing is stored, deliberately. A proposal written to `persona` and then
    presented for approval is a persona that took effect before anybody agreed to it —
    and the difference matters most in the case where the model is wrong. The cost is
    that leaving this screen loses the proposal and re-running it spends tokens again;
    that is the right side of the trade, and it is recorded rather than hidden.

    Never raises on a model failure. `propose_persona` converts every one into a named
    unavailable state, because this is a request handler and the honest answer to "the
    model is down" is a screen that says so with the fields left editable.
    """
    async with scoped_connection(scope) as session:
        stored = (
            (await session.execute(text("SELECT question_key, value FROM onboarding_answer")))
            .mappings()
            .all()
        )
        domain = (
            await session.execute(
                text("SELECT domain FROM workspace WHERE id = :ws"),
                {"ws": str(scope.workspace_id)},
            )
        ).scalar_one_or_none()

    answers: dict[str, object] = {row["question_key"]: row["value"] for row in stored}

    # The crawl target is the workspace's *own* domain, or the URL its own setup
    # answer gave. Never a value from this request: a client-supplied URL here would
    # make this endpoint an SSRF primitive with a language model attached, and the
    # guard in `connectors/ssrf.py` should not be the only thing standing in the way.
    target = _as_url(answers.get("company_url")) or (f"https://{domain}" if domain else None)

    page_text, page_url = await _fetch_own_page(target, settings)
    proposal = await propose_persona(
        provider, answers=answers, page_text=page_text, page_url=page_url
    )

    return PersonaProposalOut(
        summary=proposal.summary,
        priority_topics=list(proposal.priority_topics),
        communication_style=(
            proposal.communication_style.value if proposal.communication_style else None
        ),
        default_landing_screen=(
            proposal.default_landing_screen.value if proposal.default_landing_screen else None
        ),
        available=proposal.available,
        unavailable_reason=proposal.unavailable_reason,
        provenance=list(proposal.provenance),
    )


def _as_url(value: object) -> str | None:
    return value if isinstance(value, str) and value.startswith(("http://", "https://")) else None


async def _fetch_own_page(target: str | None, settings: Settings) -> tuple[str | None, str | None]:
    """Fetch the workspace's own page, or return nothing and say so in the log.

    A failed crawl is not a failed persona. The profile agent still has the answers
    the user typed, so the proposal degrades to those rather than to an error — which
    is the difference between "we could not read your site" and "setup is broken".
    """
    if target is None:
        return None, None

    try:
        page = await fetch_page(
            target,
            max_bytes=settings.crawl_max_bytes,
            timeout_seconds=settings.crawl_timeout_seconds,
            max_redirects=settings.crawl_max_redirects,
        )
    except FetchError as exc:
        log.info("agents.persona.crawl_failed", reason=type(exc).__name__)
        return None, None

    signals = extract_signals(page.html, url=page.final_url)
    # `text_sample` is the leading body text, and its own docstring already called it
    # "untrusted content — see the M12 boundary". This is the first caller to actually
    # honour that: it goes to `wrap_untrusted` and nowhere else.
    #
    # It is capped at 2000 characters upstream, well under `MAX_CRAWL_CHARS`, so the
    # agent sees a page's opening rather than its whole text. That is a real limit on
    # what the summary can know, and the reason the proposal is editable.
    return signals.text_sample, page.final_url


@router.post(
    "/onboarding/persona",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def save_persona(payload: PersonaIn, scope: CurrentScope) -> Response:
    """Store the persona this person confirmed.

    Per user *and* per workspace: `uq_persona_workspace_user`, so the same person in
    two workspaces has two personas and neither leaks into the other.

    **A persona changes emphasis, never access.** Doc 06 §2.6 is explicit, and
    `test_persona_and_invitations.py` asserts the enforcement by walking
    `ScopedSession`, the access rule and the scope table for persona field names.
    Nothing in this handler touches `membership`, which is the only thing
    `build_scope` reads.
    """
    style = _one_of(payload.communication_style, CommunicationStyle, "communication style")
    landing = _one_of(payload.default_landing_screen, LandingScreen, "landing screen")
    topics = [
        item
        for raw in payload.priority_topics[:MAX_LIST_ITEMS]
        if (item := raw.strip()[:MAX_ITEM_LENGTH])
    ]

    async with scoped_connection(scope) as session:
        await session.execute(
            text(
                "INSERT INTO persona"
                " (workspace_id, user_id, stated_purpose, priority_topics,"
                "  default_landing_screen, communication_style, language, timezone)"
                " VALUES (:ws, :u, :purpose, :topics, :landing, :style, :lang, :tz)"
                " ON CONFLICT (workspace_id, user_id) DO UPDATE"
                "    SET stated_purpose = EXCLUDED.stated_purpose,"
                "        priority_topics = EXCLUDED.priority_topics,"
                "        default_landing_screen = EXCLUDED.default_landing_screen,"
                "        communication_style = EXCLUDED.communication_style,"
                "        language = EXCLUDED.language,"
                "        timezone = EXCLUDED.timezone,"
                "        updated_at = now()"
            ),
            {
                "ws": str(scope.workspace_id),
                # The session's user, never a field from the request. A persona is
                # personal, and an id here would let one member rewrite another's.
                "u": str(scope.user_id),
                "purpose": payload.stated_purpose,
                "topics": topics,
                "landing": landing.value if landing else None,
                "style": style.value if style else None,
                "lang": payload.language.strip() or "en",
                "tz": payload.timezone.strip() or "Asia/Muscat",
            },
        )

    log.info("onboarding.persona.saved", topics=len(topics), has_style=style is not None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _one_of(value: str | None, choices: type[StrEnum], label: str) -> StrEnum | None:
    """Accept a value from the enum, or refuse. Never coerce.

    Coercion is how a preference nobody expressed ends up stored — "conversational"
    quietly becoming `brief`.
    """
    if value is None or not value.strip():
        return None
    try:
        return choices(value.strip().lower())
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{value!r} is not a valid {label}."
        ) from None


class ConnectionOut(BaseModel):
    source: str
    label: str
    connected: bool
    """Always false. There is no connector, and a field that could only ever be
    false is still worth sending: the client renders state from data rather than
    hard-coding an assumption it would then have to remember to remove."""

    unlocks: int
    """How many capabilities this would make reachable, counted from the same
    offering definitions the dashboards render."""

    departments: list[str]
    """Which directors those capabilities sit under."""

    detail: str


class ConnectionsOut(BaseModel):
    connections: list[ConnectionOut]
    connected_count: int
    """Zero, and stated rather than implied."""


@router.get("/onboarding/connections", response_model=ConnectionsOut)
async def connections(scope: CurrentScope) -> ConnectionsOut:
    """What connecting each tool would unlock, and that none of them is connected.

    Doc 04 §5's stage 4. **No OAuth, and no fake connected state** — M10 is unbuilt
    and both its prerequisites are open decisions (**D3** Google credentials, **D10**
    which CRM). So this is the honest version: name each tool, count what it would
    actually unlock, and say plainly that nothing is attached.

    The counts come from `offerings_needing`, which reads the same offering
    definitions the director pages render. A hand-written "connect GA4 to unlock 6
    things" would be a number that goes stale the first time doc 05's spec changes —
    and it went stale in the other direction already: `Source.SEARCH_CONSOLE`
    unlocked *nothing* until offering 3.7's `needs` was corrected, so this endpoint
    would have offered a tool that changes no tile.

    Read-only, and it discloses no workspace data — only the shape of the product.
    It still takes a `ScopedSession`, because everything under a workspace does.
    """
    out: list[ConnectionOut] = []
    for source in CONNECTABLE:
        offerings = offerings_needing(source)
        departments = sorted(
            {
                director.department.value
                for director in DIRECTORS
                for offering in director.offerings
                if offering in offerings
            }
        )
        out.append(
            ConnectionOut(
                source=source.value,
                label=TOOL_LABELS[source.value],
                connected=False,
                unlocks=len(offerings),
                departments=departments,
                detail=(
                    "Not connected. No connector is built yet, so this stays locked "
                    "however you answer."
                ),
            )
        )

    log.info("onboarding.connections.listed", tools=len(out), connected=0)
    return ConnectionsOut(connections=out, connected_count=0)


@router.get("/onboarding/questions", response_model=QuestionsOut)
async def questions(scope: CurrentScope) -> QuestionsOut:
    """Every question, plus whatever of it this caller may see.

    One request drives the whole wizard. The stages are returned together and
    ordered by the client, because the sequencing doc 04 §5 asks for — audit
    first, money questions after — is a matter of when a screen is *shown*.
    The one ordering rule that is not cosmetic, that brief recipients must be
    existing workspace users (doc 06 §4.10), is enforced on the write instead,
    where a client cannot route around it.
    """
    administers = may_administer(scope.role)

    async with scoped_connection(scope) as session:
        stored = (
            (
                await session.execute(
                    text("SELECT question_key, value, scope, department FROM onboarding_answer")
                )
            )
            .mappings()
            .all()
        )
        # Sink-backed questions live in their real columns, so they have to be read
        # from there or the wizard would render them blank on every reload and
        # invite the user to type their own name again.
        #
        # One statement, and `app_user` is joined on the *session's* user id — not
        # a join across the membership table, which would make this a company
        # directory the endpoint was never asked to be.
        sinks = (
            await session.execute(
                text(
                    "SELECT w.name AS workspace_name, u.display_name"
                    "  FROM workspace w, app_user u"
                    " WHERE w.id = :ws AND u.id = :u"
                ),
                {"ws": str(scope.workspace_id), "u": str(scope.user_id)},
            )
        ).first()
        # Only administrators choose brief recipients, so only they need the
        # roster. Returning it to everyone would make this endpoint a company
        # directory that nothing asked for.
        members = await _members(session) if administers else []

    answers: dict[str, Any] = {}
    for row in stored:
        question = BY_KEY.get(row["question_key"])
        if question is None:
            continue  # a key retired from the catalogue; nothing can render it
        # The stored classification decides, not the catalogue's current one. If
        # a question is reclassified later, rows written under the old scope keep
        # it until something migrates them — reading them at the new, possibly
        # weaker, scope would disclose them retroactively.
        stored_scope = scope_from_code(row["scope"])
        stored_department = Department(row["department"]) if row["department"] else None
        if may_read_answer(scope, stored_scope, stored_department):
            answers[row["question_key"]] = row["value"]

    for question in CATALOGUE:
        if question.sink is Sink.ANSWER or sinks is None:
            continue
        # Read through the same permission check as any other answer. Both of these
        # are L1/L2 and so reachable by everyone who can see the workspace, but
        # deciding it here rather than assuming it means a later reclassification
        # cannot leave a value visible that the catalogue no longer permits.
        if not may_read_answer(scope, question.scope, question.department):
            continue
        value = sinks.workspace_name if question.sink is Sink.WORKSPACE_NAME else sinks.display_name
        if value:
            answers[question.key] = value

    selected = departments_selected(answers)

    return QuestionsOut(
        can_administer=administers,
        members=members,
        questions=[
            QuestionOut(
                key=q.key,
                prompt=q.prompt,
                stage=q.stage.value,
                answer_type=q.answer_type.value,
                scope=scope_code(q.scope),
                department=q.department.value if q.department else None,
                asked_of=q.asked_of.value if q.asked_of else None,
                required=q.required,
                why=q.why,
                options=[ChoiceOut(value=c.value, label=c.label) for c in q.options],
                free_entry=q.free_entry,
                writable=administers and may_read_answer(scope, q.scope, q.department),
                value=answers.get(q.key),
            )
            for q in CATALOGUE
            # Absent, not disabled. A department the company does not run, or that
            # this caller cannot reach, produces no rows here at all.
            if may_be_asked(scope, q, selected)
        ],
    )


@router.post(
    "/onboarding/answers",
    response_model=SavedOut,
    dependencies=[Depends(require_csrf)],
)
async def save_answers(payload: AnswersIn, scope: CurrentScope) -> SavedOut:
    """Store a wizard step's answers, each tagged with its own classification.

    Validated in full before anything is written. A step that half-saved would
    leave the user looking at a form that disagrees with the database about what
    they just told it.
    """
    questions_to_write: list[tuple[Question, Any]] = []

    async with scoped_connection(scope) as session:
        member_ids = frozenset(m.user_id for m in await _members(session))

        for answer in payload.answers:
            question = BY_KEY.get(answer.key)
            if question is None:
                # `scope_for_answer` would raise; this is the same refusal with
                # a status code. Never store an answer at a guessed scope.
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown question: {answer.key}")
            ensure_may_answer(scope, question)
            questions_to_write.append(
                (question, validate_answer(question, answer.value, member_ids=member_ids))
            )

        # The write path has to narrow by selection too, or it goes asymmetric with
        # the read path: `GET /onboarding/questions` never offers a department the
        # company did not select, so an answer for one could only arrive from a
        # client that built the request itself — and it would then be **stored,
        # classified, and invisible**, because the same filter hides it on the way
        # back out. That is the shape of every silent-state defect in this codebase.
        #
        # Resolved against the selection *as it will be after this batch*, not as it
        # is now. A client is entitled to send `departments_run` and that department's
        # answers in one request, and refusing the second half of its own batch would
        # be an ordering trap rather than a rule.
        selected = _selection_after(dict(questions_to_write), await _stored_selection(session))
        for question, _ in questions_to_write:
            if question.asked_of is not None and question.asked_of not in selected:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{question.asked_of.value.title()} is not one of the departments "
                    "this workspace runs.",
                )

        for question, value in questions_to_write:
            await store_answer(session, caller=scope, question=question, value=value)

    log.info("onboarding.answers.saved", count=len(questions_to_write))
    return SavedOut(saved=[q.key for q, _ in questions_to_write])


# ── Invitations ───────────────────────────────────────────────


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role
    departments: list[Department] = Field(default_factory=list, max_length=len(Department))


class InvitationOut(BaseModel):
    invitation_id: UUID
    email: str
    role: str
    departments: list[str]
    state: str
    expires_at: str


class IssuedOut(InvitationOut):
    accept_path: str
    """Where to send the invited person.

    Returned to the inviter because no email is sent yet — delivery is not wired
    up anywhere in the product. Handing the link back is not a weakening: the
    inviter is the person who chose the role, and the link alone grants nothing,
    since acceptance requires being signed in as the address it names.
    """


class InvitationsOut(BaseModel):
    invitations: list[InvitationOut]


def _out(invitation: invites.Invitation) -> InvitationOut:
    return InvitationOut(
        invitation_id=invitation.id,
        email=invitation.email,
        role=invitation.role.value,
        departments=sorted(d.value for d in invitation.departments),
        state=invitation.state,
        expires_at=invitation.expires_at.isoformat(),
    )


@router.post(
    "/invitations",
    response_model=IssuedOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_invitation(payload: InviteIn, scope: CurrentScope) -> IssuedOut:
    """Invite someone, at a role this caller is allowed to grant.

    Every precondition is in `check_invitation` rather than here, so there is
    one function to audit rather than one per route — the same arrangement as
    `create_workspace_for_claim`.
    """
    try:
        departments = check_invitation(scope, role=payload.role, departments=payload.departments)
    except InvitationError as exc:
        # "Not found" is the department-unreachable case, which must not confirm
        # that the department exists.
        if str(exc) == "Not found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    email = payload.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That is not an email address.")

    async with scoped_connection(scope) as session:
        issued = await invites.issue(
            session,
            workspace_id=scope.workspace_id,
            invited_by_user_id=scope.user_id,
            email=email,
            role=payload.role,
            departments=departments,
        )

    return IssuedOut(
        **_out(issued.invitation).model_dump(),
        accept_path=f"/invitations/accept?token={issued.token}",
    )


@router.get("/invitations", response_model=InvitationsOut)
async def list_invitations(scope: CurrentScope) -> InvitationsOut:
    """Who has been invited, and what became of it.

    Administrators only. An invitation names a person and the role someone chose
    for them, which is not a fact the rest of the workspace is owed.
    """
    if not may_administer(scope.role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    async with scoped_connection(scope) as session:
        found = await invites.list_for_workspace(session)

    return InvitationsOut(invitations=[_out(i) for i in found])


@router.post(
    "/invitations/{invitation_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def revoke_invitation(invitation_id: UUID, scope: CurrentScope) -> Response:
    if not may_administer(scope.role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    async with scoped_connection(scope) as session:
        changed = await invites.revoke(session, invitation_id=invitation_id)

    if not changed:
        # Either it is not in this workspace, or it is already accepted or
        # revoked. One answer for all three: the first is an isolation boundary
        # and the other two are simply nothing to do.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


class AcceptIn(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    # No role. No department. No workspace. Doc 06 §2.2 — acceptance copies what
    # the inviter set, and a field here is the escalation it warns about.


class AcceptOut(BaseModel):
    outcome: str
    workspace_id: UUID | None
    workspace_name: str | None
    role: str | None


@router.post(
    "/invitations/accept",
    response_model=AcceptOut,
    dependencies=[Depends(require_csrf)],
)
async def accept_invitation(payload: AcceptIn, session: CurrentSession) -> AcceptOut:
    """Join a workspace.

    Depends on `current_session`, not `current_scope`, and that is the whole
    shape of the problem: the caller has no workspace yet, so `current_scope`
    would refuse them 403 before they could get one. `current_session` grants
    authority over nothing but their own identity, and no `ScopedSession` can be
    built from it — so this route structurally cannot read workspace data,
    which is exactly the guarantee wanted for a route that takes a token from a
    stranger.
    """
    async with _unscoped_session() as db:
        result = await invites.accept(db, token=payload.token, user_id=session.user_id)

        if result.outcome is invites.AcceptOutcome.ACCEPTED and result.workspace_id:
            # Land them in the workspace they just joined. The session row is the
            # only place the active workspace lives (doc 06 §2.1).
            await db.execute(
                text("UPDATE user_session SET active_workspace_id = :ws WHERE id = :sid"),
                {"ws": str(result.workspace_id), "sid": str(session.session_id)},
            )

        await db.commit()

    if result.outcome is invites.AcceptOutcome.UNUSABLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That invitation link is no longer valid. Ask for a new one.",
        )
    if result.outcome is invites.AcceptOutcome.WRONG_ACCOUNT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This invitation was sent to a different email address. "
            "Sign in with that address to accept it.",
        )

    return AcceptOut(
        outcome=result.outcome.value,
        workspace_id=result.workspace_id,
        workspace_name=result.workspace_name,
        role=result.role.value if result.role else None,
    )
