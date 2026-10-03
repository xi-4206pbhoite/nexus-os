"""Serving a signed URL. The one route in the product with no session.

`storage.signed_url` has minted `/files/{key}?expires=…&sig=…` since M2 and
nothing has ever served it, so every signed URL in the codebase pointed at a
404. This is that endpoint.

**Unauthenticated on purpose, and that is the whole design.** The signature is
the authorisation: `/documents/{id}/download` decides *once*, against the
uploader, whether this caller may have this document, and mints a URL that says
so. A browser then fetches it without cookies — which is what makes the same
contract work against S3 in production, where the bytes never pass through us.

Three properties that make that safe, each with a test:

- **The signature covers the key**, so a URL signed for one document cannot be
  edited into a URL for another.
- **It covers the expiry**, so the deadline cannot be extended by the person
  holding the link.
- **A bad signature and a missing file answer identically.** Otherwise this
  becomes an oracle for which keys exist — and keys contain workspace ids.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.config import Settings, get_settings
from app.logging import get_logger
from app.storage import FilesystemObjectStore

router = APIRouter(prefix="/files", tags=["files"])
log = get_logger(__name__)


@router.get("/{key:path}")
async def serve_signed(
    key: str,
    settings: Annotated[Settings, Depends(get_settings)],
    expires: Annotated[int, Query()],
    sig: Annotated[str, Query()],
) -> Response:
    store = FilesystemObjectStore(settings.storage_root, settings.require("storage_signing_secret"))

    # One refusal for an invalid signature, an expired link, an unsafe key and a
    # file that is not there. Telling them apart would confirm which keys exist,
    # and a key contains the workspace id that owns it.
    if not store.verify_signed_url(key, expires, sig):
        log.info("files.refused")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    try:
        data = store.get(key)
    except (FileNotFoundError, ValueError, OSError):
        log.info("files.missing")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None

    return Response(
        content=data,
        # `octet-stream` rather than the uploaded content type, which the store
        # does not keep. Serving the browser a type the uploader chose is the
        # thing `nosniff` and `attachment` are here to prevent anyway, so the
        # honest type is the one that makes the browser download it.
        media_type="application/octet-stream",
        headers={
            # Never inline. A document rendered in the browser at our origin is
            # stored HTML running as us if it is HTML, and the uploader chose
            # the file, not us.
            "Content-Disposition": "attachment",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
