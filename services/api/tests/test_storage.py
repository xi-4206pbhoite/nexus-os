"""Object storage contract.

The traversal cases matter beyond ordinary hygiene: a key that escapes its
workspace prefix is a cross-tenant read, which is the failure mode M1's
isolation suite exists to prevent. Closing it at the storage layer as well as
the query layer is defence in depth, not duplication.
"""

from __future__ import annotations

import time
from pathlib import Path
from uuid import UUID

import pytest

from app.storage import (
    FilesystemObjectStore,
    StorageKeyError,
    workspace_key,
)

WS = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WS = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def store(tmp_path: Path) -> FilesystemObjectStore:
    return FilesystemObjectStore(tmp_path / "storage", signing_secret="test-secret")


def test_round_trip(store: FilesystemObjectStore) -> None:
    key = workspace_key(WS, "documents", "rate-card.pdf")
    stored = store.put(key, b"%PDF-1.7 fake", content_type="application/pdf")

    assert stored.size_bytes == 13
    assert store.exists(key)
    assert store.get(key) == b"%PDF-1.7 fake"

    store.delete(key)
    assert not store.exists(key)


def test_keys_are_workspace_prefixed(store: FilesystemObjectStore) -> None:
    a = workspace_key(WS, "documents", "x.pdf")
    b = workspace_key(OTHER_WS, "documents", "x.pdf")
    assert a != b
    assert str(WS) in a and str(OTHER_WS) in b


@pytest.mark.parametrize("segment", ["../escape", "/absolute", "..", "a/../../b", ""])
def test_unsafe_key_segments_are_rejected(segment: str) -> None:
    with pytest.raises(StorageKeyError):
        workspace_key(WS, "documents", segment)


@pytest.mark.parametrize("key", ["../outside.txt", "/etc/passwd", "ws/../../secrets"])
def test_traversal_is_rejected_at_the_driver(store: FilesystemObjectStore, key: str) -> None:
    with pytest.raises(StorageKeyError):
        store.put(key, b"x", content_type="text/plain")


def test_signed_url_verifies(store: FilesystemObjectStore) -> None:
    key = workspace_key(WS, "documents", "a.pdf")
    store.put(key, b"x", content_type="application/pdf")

    url = store.signed_url(key, ttl_seconds=300)
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("sig=")[1]

    assert store.verify_signed_url(key, expires, signature)


def test_signature_is_bound_to_the_key(store: FilesystemObjectStore) -> None:
    """A signature for one object must not open another."""
    key_a = workspace_key(WS, "documents", "a.pdf")
    key_b = workspace_key(OTHER_WS, "documents", "b.pdf")
    for k in (key_a, key_b):
        store.put(k, b"x", content_type="application/pdf")

    url = store.signed_url(key_a, ttl_seconds=300)
    expires = int(url.split("expires=")[1].split("&")[0])
    signature = url.split("sig=")[1]

    assert not store.verify_signed_url(key_b, expires, signature)


def test_expired_signature_is_rejected(store: FilesystemObjectStore) -> None:
    key = workspace_key(WS, "documents", "a.pdf")
    store.put(key, b"x", content_type="application/pdf")

    # Reaching into the private signer is deliberate: minting a genuinely
    # expired signature is the only way to prove expiry is checked.
    past = int(time.time()) - 1
    signature = store._signature(key, past)
    assert not store.verify_signed_url(key, past, signature)


def test_tampered_signature_is_rejected(store: FilesystemObjectStore) -> None:
    key = workspace_key(WS, "documents", "a.pdf")
    store.put(key, b"x", content_type="application/pdf")

    url = store.signed_url(key, ttl_seconds=300)
    expires = int(url.split("expires=")[1].split("&")[0])

    assert not store.verify_signed_url(key, expires, "0" * 64)
