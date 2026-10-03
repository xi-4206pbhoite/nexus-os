"""The document list and the signed download.

Two things `doc/12` P8 calls out as built-but-unreachable: `DocumentSummary`
was declared and never returned by any route, and `storage.signed_url` — which
mints expiring URLs and has done since M2 — had **no caller anywhere in the
codebase**. Both are now wired, which is the difference between a feature
existing and a feature working.

**The list is the caller's own uploads.** RLS makes `document` workspace-wide,
and that is right for the row: a workspace's storage quota is shared, so the
bytes are everyone's business. The *filename* is not. "Salary review 2026.xlsx"
names its contents well enough that listing it to the whole company would leak
what the chunk-level withholding (I4, L5 uploader-only) exists to protect —
and `chunks_held_for_review` is a personal count in the first place. A reviewer
still sees what has been **proposed** for workspace visibility, through the
review queue, which is the surface built for exactly that.

**A download URL expires.** A signed URL that never expires is a permanent
public link to a private document the moment it is pasted anywhere.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage import FilesystemObjectStore

SECRET = "a-signing-secret-for-tests"


@pytest.fixture
def store(tmp_path: Path) -> FilesystemObjectStore:
    return FilesystemObjectStore(tmp_path, SECRET)


def test_a_signed_url_carries_an_expiry_and_a_signature(store: FilesystemObjectStore) -> None:
    store.put("ws/documents/one", b"hello", content_type="text/plain")
    url = store.signed_url("ws/documents/one", ttl_seconds=300)

    assert "expires=" in url and "sig=" in url


def test_a_signature_for_one_key_does_not_open_another(store: FilesystemObjectStore) -> None:
    """The attack a naive signing scheme allows: sign what you may read, then
    swap the key. The signature has to cover the key, not merely accompany it."""
    store.put("ws/documents/mine", b"mine", content_type="text/plain")
    store.put("ws/documents/theirs", b"theirs", content_type="text/plain")

    url = store.signed_url("ws/documents/mine", ttl_seconds=300)
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("sig=")[1]

    assert store.verify_signed_url("ws/documents/mine", expires, signature)
    assert not store.verify_signed_url("ws/documents/theirs", expires, signature)


def test_an_expired_url_is_refused(store: FilesystemObjectStore) -> None:
    """A link that never expires is a permanent public URL to a private
    document the moment somebody pastes it into a chat."""
    store.put("ws/documents/one", b"hello", content_type="text/plain")
    url = store.signed_url("ws/documents/one", ttl_seconds=-1)
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("sig=")[1]

    assert not store.verify_signed_url("ws/documents/one", expires, signature)


def test_a_tampered_expiry_does_not_extend_the_link(store: FilesystemObjectStore) -> None:
    """Extending the deadline has to invalidate the signature, or the deadline
    is a suggestion the holder of the link can overrule."""
    store.put("ws/documents/one", b"hello", content_type="text/plain")
    url = store.signed_url("ws/documents/one", ttl_seconds=60)
    signature = url.split("sig=")[1]

    assert not store.verify_signed_url("ws/documents/one", int(time.time()) + 86400, signature)


# ── The route that serves them ────────────────────────────────


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FilesystemObjectStore]]:
    """An app whose storage is a temporary directory."""
    from app.config import Settings, get_settings
    from app.main import create_app

    app = create_app()
    base = get_settings()

    def settings() -> Settings:
        return base.model_copy(update={"storage_root": tmp_path, "storage_signing_secret": SECRET})

    app.dependency_overrides[get_settings] = settings
    store = FilesystemObjectStore(tmp_path, SECRET)
    store.put("ws/documents/one", b"the contents", content_type="text/plain")
    with TestClient(app) as client:
        yield client, store
    app.dependency_overrides.clear()


def _parts(url: str) -> tuple[str, int, str]:
    path, query = url.split("?", 1)
    bits = dict(part.split("=", 1) for part in query.split("&"))
    return path, int(bits["expires"]), bits["sig"]


def test_a_valid_signed_url_serves_the_bytes(
    served: tuple[TestClient, FilesystemObjectStore],
) -> None:
    """`storage.signed_url` has minted these since M2 and **nothing has ever
    served one** — every signed URL in the codebase pointed at a 404."""
    client, store = served
    path, expires, sig = _parts(store.signed_url("ws/documents/one", ttl_seconds=300))

    response = client.get(path, params={"expires": expires, "sig": sig})

    assert response.status_code == 200
    assert response.content == b"the contents"


def test_the_bytes_are_never_served_inline(
    served: tuple[TestClient, FilesystemObjectStore],
) -> None:
    """A document rendered at our own origin is stored HTML running as us, if
    it is HTML — and the uploader chose the file, not us."""
    client, store = served
    path, expires, sig = _parts(store.signed_url("ws/documents/one", ttl_seconds=300))

    response = client.get(path, params={"expires": expires, "sig": sig})

    assert response.headers["content-disposition"] == "attachment"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_missing_file_and_a_bad_signature_answer_identically(
    served: tuple[TestClient, FilesystemObjectStore],
) -> None:
    """Otherwise this is an oracle for which keys exist — and a key contains
    the workspace id that owns it."""
    client, store = served
    path, expires, _ = _parts(store.signed_url("ws/documents/one", ttl_seconds=300))

    tampered = client.get(path, params={"expires": expires, "sig": "not-the-signature"})
    absent_path, absent_expires, absent_sig = _parts(
        store.signed_url("ws/documents/nothing-here", ttl_seconds=300)
    )
    absent = client.get(absent_path, params={"expires": absent_expires, "sig": absent_sig})

    assert tampered.status_code == absent.status_code == 404
    assert tampered.json() == absent.json()


def test_an_unsigned_request_is_refused(
    served: tuple[TestClient, FilesystemObjectStore],
) -> None:
    """The signature is the authorisation. Without one there is nothing here."""
    client, _ = served
    assert client.get("/files/ws/documents/one").status_code == 422
