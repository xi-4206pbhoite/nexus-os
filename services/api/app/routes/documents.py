"""Document upload — the first path that writes customer content.

Three obligations converge here, and each is enforced rather than assumed.

**Consent is a precondition, not a checkbox we log.** Doc 06 §5 requires the
customer to warrant their right to use what they upload, and migration 0007
backs it with `ck_document_consent_before_indexing`: a document cannot reach
`indexed` without `consent_given_at`. The practical control this represents is
someone indexing a competitor's leaked price list — the warranty makes that
their decision rather than ours.

**Failure is visible, always.** Doc 07 M5 requires a scanned PDF with no text
layer, an over-size file and a corrupt file to each say so. A silent failure is
worse than a loud one: the customer believes the document is searchable when it
is not, and finds out when an answer omits it — which reads as the product being
wrong rather than the upload having failed.

**Classification defaults to deny (I4).** Every chunk routes through
`classify_chunk`, which withholds to L5 plus the review queue on any parse
failure, classifier failure, or confidence below threshold.

What this module deliberately does *not* do is embed. That is task 5.6, and it
is a separate step because embedding is slow, needs a model, and must not sit
between the customer and their upload confirmation.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import CursorResult, text

from app.auth.csrf import require_csrf
from app.config import Settings, get_settings
from app.deps import CurrentScope
from app.documents.chunk import Chunk, chunk_document
from app.documents.classify import (
    Classification,
    ClassificationInput,
    ReviewState,
    classify_chunk,
    review_state_code,
)
from app.documents.parse import MAX_FILE_BYTES, ParseOutcome, parse_document
from app.documents.status import DocumentStatus
from app.domain import audit
from app.domain.access import Sensitivity
from app.domain.scopes import Scope, scope_code
from app.domain.session import ScopedSession
from app.logging import get_logger
from app.retrieval.scoped import scoped_connection
from app.storage import FilesystemObjectStore, ObjectStore, workspace_key

router = APIRouter(prefix="/documents", tags=["documents"])
log = get_logger(__name__)

CONSENT_TEXT_VERSION = "2026-08-18.v1"
"""Bumped whenever the warranty wording changes.

Stored per document, because "they consented" means little without *what* they
consented to. A later dispute is about the wording in force at the time.
"""

CONSENT_WARRANTY = (
    "I warrant that this workspace has the right to use and index this document, "
    "and that doing so breaches no confidentiality obligation or third-party right."
)


class UploadOut(BaseModel):
    document_id: UUID
    filename: str
    status: str
    chunks_indexed: int
    chunks_held_for_review: int
    page_count: int | None
    message: str
    """Empty when the upload succeeded. Never empty when it did not."""


class DocumentSummary(BaseModel):
    document_id: UUID
    filename: str
    status: str
    page_count: int | None
    failure_reason: str | None
    created_at: datetime
    chunks_held_for_review: int


def _object_store(settings: Settings) -> ObjectStore:
    return FilesystemObjectStore(
        settings.storage_root,
        settings.require("storage_signing_secret"),
    )


@router.post(
    "",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_document(
    scope: CurrentScope,
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form()] = False,
    supersedes_id: Annotated[UUID | None, Form()] = None,
) -> UploadOut:
    """Accept a document, parse it, classify every chunk, store it.

    `consent` must be true, and is a form field rather than an implicit property
    of the request: an upload that consents by virtue of being an upload is not
    a warranty anyone could rely on.
    """
    if not consent:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Confirm you have the right to use this document before uploading it.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"This file is over {MAX_FILE_BYTES // (1024 * 1024)} MB. "
            "Split it and upload the parts.",
        )

    filename = file.filename or "untitled"
    parsed = parse_document(data, filename=filename)
    digest = hashlib.sha256(data).hexdigest()

    document_id = uuid4()
    key = workspace_key(scope.workspace_id, "documents", str(document_id))

    # Stored whether or not parsing worked. A file we could not read is still
    # the customer's file, and discarding it because our parser failed would
    # lose something they believe they gave us.
    _object_store(settings).put(
        key, data, content_type=file.content_type or "application/octet-stream"
    )

    if not parsed.succeeded:
        await _record(
            document_id=document_id,
            scope=scope,
            filename=filename,
            content_type=file.content_type,
            size_bytes=len(data),
            storage_key=key,
            digest=digest,
            state=(
                DocumentStatus.QUARANTINED
                if parsed.outcome is ParseOutcome.UNSUPPORTED_TYPE
                else DocumentStatus.FAILED
            ),
            failure_reason=parsed.message,
            page_count=parsed.page_count or None,
            supersedes_id=supersedes_id,
        )
        log.info("document.parse_failed", outcome=parsed.outcome.value)
        return UploadOut(
            document_id=document_id,
            filename=filename,
            status="failed",
            chunks_indexed=0,
            chunks_held_for_review=0,
            page_count=parsed.page_count or None,
            message=parsed.message,
        )

    classified = _classify_all(chunk_document(parsed.pages), scope=scope)

    await _record(
        document_id=document_id,
        scope=scope,
        filename=filename,
        content_type=file.content_type,
        size_bytes=len(data),
        storage_key=key,
        digest=digest,
        state=DocumentStatus.INDEXED,
        failure_reason=None,
        page_count=parsed.page_count,
        supersedes_id=supersedes_id,
        chunks=classified,
    )

    held = sum(1 for _, c in classified if c.review_state is not ReviewState.AUTO_APPROVED)
    log.info(
        "document.indexed",
        chunks=len(classified),
        held_for_review=held,
        page_count=parsed.page_count,
    )

    return UploadOut(
        document_id=document_id,
        filename=filename,
        status="indexed",
        chunks_indexed=len(classified) - held,
        chunks_held_for_review=held,
        page_count=parsed.page_count,
        message="",
    )


def _classify_all(
    chunks: list[Chunk], *, scope: ScopedSession
) -> list[tuple[Chunk, Classification]]:
    """Classify every chunk, defaulting to deny.

    No classifier model exists yet, so nothing is *suggested* with confidence
    and `classifier_failed` is set on every input. Everything therefore
    withholds to L5 plus the review queue — which is I4 working exactly as
    intended. The absence of a classifier is a reason to deny, not a reason to
    default to visible, and task 5.4's model swaps in here without any caller
    changing.
    """
    return [
        (
            chunk,
            classify_chunk(
                ClassificationInput(
                    text=chunk.text,
                    suggested_scope=Scope.L5_PERSONAL,
                    suggested_department=None,
                    suggested_sensitivity=Sensitivity.NORMAL,
                    confidence=0.0,
                    classifier_failed=True,
                ),
                uploader_id=str(scope.user_id),
            ),
        )
        for chunk in chunks
    ]


_INSERT_DOCUMENT = text(
    "INSERT INTO document"
    " (id, workspace_id, uploaded_by_user_id, filename, content_type, size_bytes,"
    "  storage_key, content_sha256, status, consent_given_at, consent_text_version,"
    "  failure_reason, page_count, supersedes_id)"
    " VALUES (:id, :ws, :user, :filename, :content_type, :size, :key, :digest,"
    "         :status, :consent_at, :consent_version, :failure, :pages, :supersedes)"
)

_INSERT_CHUNK = text(
    "INSERT INTO chunk"
    " (workspace_id, document_id, source_page, source_label, ordinal, content,"
    "  token_estimate, scope, department, owner_user_id, sensitivity,"
    "  classified_by, confidence, review_state)"
    " VALUES (:ws, :doc, :page, :label, :ordinal, :content, :tokens, :scope,"
    "         :department, :owner, :sensitivity, :classified_by, :confidence, :review)"
)


async def _record(
    *,
    document_id: UUID,
    scope: ScopedSession,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    storage_key: str,
    digest: str,
    state: DocumentStatus,
    failure_reason: str | None,
    page_count: int | None,
    supersedes_id: UUID | None,
    chunks: list[tuple[Chunk, Classification]] | None = None,
) -> None:
    """Write the document and its chunks in one transaction, under RLS.

    Through `scoped_connection`, the architecture's mandatory path for customer
    data, which until now had no production caller. That matters beyond
    convention here: the GUCs it sets are what the WITH CHECK half of the
    isolation policy reads, so a bug aiming these rows at another workspace is
    refused by Postgres rather than by our own care.

    One transaction covers the document and every chunk. A partial write would
    leave a document claiming to be `indexed` with only part of its content
    reachable - the silent-failure shape doc 07 M5 forbids.
    """
    consent_at = datetime.now(UTC) if state is DocumentStatus.INDEXED else None

    async with scoped_connection(scope) as session:
        await session.execute(
            _INSERT_DOCUMENT,
            {
                "id": str(document_id),
                "ws": str(scope.workspace_id),
                "user": str(scope.user_id),
                "filename": filename,
                "content_type": content_type or "application/octet-stream",
                "size": size_bytes,
                "key": storage_key,
                "digest": digest,
                "status": state.value,
                # Only on the indexed path. The check constraint requires it
                # there, and a failed upload was never indexed, so recording
                # consent for it would overstate what happened.
                "consent_at": consent_at,
                "consent_version": CONSENT_TEXT_VERSION if consent_at else None,
                "failure": failure_reason,
                "pages": page_count,
                "supersedes": str(supersedes_id) if supersedes_id else None,
            },
        )

        for chunk, classification in chunks or []:
            await session.execute(
                _INSERT_CHUNK,
                {
                    "ws": str(scope.workspace_id),
                    "doc": str(document_id),
                    "page": chunk.page_number,
                    "label": chunk.page_label,
                    "ordinal": chunk.ordinal,
                    "content": chunk.text,
                    "tokens": max(1, (chunk.char_end - chunk.char_start) // 4),
                    "scope": scope_code(classification.scope),
                    "department": (
                        [classification.department.value] if classification.department else []
                    ),
                    "owner": classification.owner_user_id,
                    "sensitivity": classification.sensitivity.value,
                    "classified_by": classification.classified_by,
                    "confidence": classification.confidence,
                    "review": review_state_code(classification.review_state),
                },
            )

        await audit.record(
            session,
            workspace_id=scope.workspace_id,
            action=audit.AuditAction.DOCUMENT_UPLOADED,
            actor_user_id=scope.user_id,
            target_type="document",
            target_id=str(document_id),
        )

        if supersedes_id is not None:
            # Doc 06 s6 - a superseded document does not hand its scope to its
            # replacement. The replacement was classified from scratch above;
            # this only retires the old one, so its chunks stop being reachable
            # while the row survives for provenance.
            await session.execute(
                text(
                    "UPDATE document SET status = :superseded"
                    " WHERE id = :old AND workspace_id = :ws"
                ),
                {
                    "superseded": DocumentStatus.SUPERSEDED.value,
                    "old": str(supersedes_id),
                    "ws": str(scope.workspace_id),
                },
            )


# ── The review queue (task 5.8) ───────────────────────────────


class ReviewItem(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    source_page: int | None
    source_label: str | None
    excerpt: str
    scope: str
    sensitivity: str
    confidence: float
    classified_by: str


class ReviewQueue(BaseModel):
    items: list[ReviewItem]
    total: int
    """Total pending, which may exceed the returned list — this is paged."""


@router.get("/review-queue", response_model=ReviewQueue)
async def review_queue(scope: CurrentScope, limit: int = 50) -> ReviewQueue:
    """Chunks withheld from the workspace, awaiting a human.

    Reached only through `scoped_connection`, so rows are filtered to the
    caller's workspace by the database rather than by this query. The WHERE
    clause narrows *within* that; it is not what provides the isolation.

    The excerpt is truncated deliberately. A reviewer needs enough to judge the
    classification, not the whole document — and this endpoint returns content
    withheld precisely because nobody has yet decided who may see it.
    """
    limit = max(1, min(limit, 200))

    async with scoped_connection(scope) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT c.id, c.document_id, d.filename, c.source_page,"
                        "       c.source_label, left(c.content, 400) AS excerpt,"
                        "       c.scope, c.sensitivity, c.confidence, c.classified_by"
                        "  FROM chunk c JOIN document d ON d.id = c.document_id"
                        "  WHERE c.review_state = :pending"
                        "  ORDER BY c.created_at DESC"
                        "  LIMIT :limit"
                    ),
                    {"limit": limit, "pending": review_state_code(ReviewState.PENDING_REVIEW)},
                )
            )
            .mappings()
            .all()
        )

        total = (
            await session.execute(
                text("SELECT count(*) FROM chunk WHERE review_state = :pending"),
                {"pending": review_state_code(ReviewState.PENDING_REVIEW)},
            )
        ).scalar_one()

    return ReviewQueue(
        items=[
            ReviewItem(
                chunk_id=r["id"],
                document_id=r["document_id"],
                filename=r["filename"],
                source_page=r["source_page"],
                source_label=r["source_label"],
                excerpt=r["excerpt"],
                scope=r["scope"],
                sensitivity=r["sensitivity"],
                confidence=r["confidence"],
                classified_by=r["classified_by"],
            )
            for r in rows
        ],
        total=int(total),
    )


class ReviewDecision(BaseModel):
    approve: bool
    scope: str | None = None
    """Where the chunk should sit if approved. Omitted leaves it at L5."""


@router.post(
    "/review-queue/{chunk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def decide_review(
    chunk_id: UUID,
    decision: ReviewDecision,
    scope: CurrentScope,
) -> Response:
    """Approve or reject a withheld chunk.

    Doc 07 M5 task 5.8: a chunk marked `personal` or `restricted` needs human
    confirmation before anyone else can reach it.

    The reviewer must hold the authority for the scope they are granting, and
    `may_reach_scope` decides that rather than this handler. Without the check
    the queue becomes a privilege-escalation route: withhold a chunk to L5, then
    promote it to L2 from an account that cannot read L2 at all.
    """
    target = _parse_scope(decision.scope) if decision.approve and decision.scope else None

    if target is not None and not scope.may_reach_scope(target):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You cannot approve a chunk into a scope you do not have access to.",
        )

    async with scoped_connection(scope) as session:
        result: CursorResult[Any] = await session.execute(  # type: ignore[assignment]
            text(
                "UPDATE chunk"
                "   SET review_state = :state,"
                "       scope = COALESCE(:scope, scope),"
                "       reviewed_by_user_id = :reviewer,"
                "       reviewed_at = now()"
                " WHERE id = :id AND review_state = :pending"
            ),
            {
                "pending": review_state_code(ReviewState.PENDING_REVIEW),
                "state": review_state_code(
                    ReviewState.APPROVED if decision.approve else ReviewState.REJECTED
                ),
                "scope": scope_code(target) if target else None,
                "reviewer": str(scope.user_id),
                "id": str(chunk_id),
            },
        )

        # Inside the same transaction and the same scoped session as the
        # decision, so a logged review is a review that happened. Skipped when
        # nothing was updated — a 404 below is "no such chunk", and logging it
        # would fill the trail with rows for actions that did not occur.
        if result.rowcount:
            await audit.record(
                session,
                workspace_id=scope.workspace_id,
                action=audit.AuditAction.REVIEW_DECISION,
                actor_user_id=scope.user_id,
                target_type="chunk",
                target_id=str(chunk_id),
                reason=(
                    f"approved into {scope_code(target)}"
                    if decision.approve and target
                    else ("approved" if decision.approve else "rejected")
                ),
            )

    if result.rowcount == 0:
        # Does not exist, belongs to another workspace (RLS made it invisible),
        # or was already decided. All three are 404: telling them apart would
        # confirm the existence of a chunk the caller cannot see.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such chunk awaiting review.")

    log.info("chunk.reviewed", approved=decision.approve)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _parse_scope(raw: str) -> Scope:
    for member in Scope:
        if member.name.split("_")[0].lower() == raw.strip().lower():
            return member
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown scope {raw!r}.")
