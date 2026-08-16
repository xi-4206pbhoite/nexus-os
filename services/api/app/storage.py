"""Object storage.

Doc 07 §3 specifies S3-compatible storage with **signed URLs only**. ADR 0001
removed the local MinIO container, so the filesystem driver below still issues
HMAC-signed, expiring URLs. That matters more than it looks: if the local driver
handed out plain paths, nothing would exercise the signed-URL contract and the
first time it ran would be in production.

Keys are always workspace-prefixed. Path traversal is rejected rather than
normalised away, because a key that tries to escape its workspace is a bug or an
attack, never a typo worth silently fixing.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlencode
from uuid import UUID

_SAFE_KEY: Final = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./")


class StorageKeyError(ValueError):
    """The key is not safely resolvable inside its workspace prefix."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    content_type: str


def workspace_key(workspace_id: UUID, *parts: str) -> str:
    """Build a key that cannot escape its workspace prefix."""
    for part in parts:
        if not part:
            raise StorageKeyError("empty key segment")
        if ".." in part or part.startswith("/"):
            raise StorageKeyError(f"unsafe key segment: {part!r}")
        if not set(part) <= _SAFE_KEY:
            raise StorageKeyError(f"key segment has disallowed characters: {part!r}")
    return "/".join(("ws", str(workspace_id), *parts))


class ObjectStore(ABC):
    """The storage contract. Application code depends on this, never on a driver."""

    @abstractmethod
    def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def signed_url(self, key: str, *, ttl_seconds: int) -> str: ...


class FilesystemObjectStore(ObjectStore):
    """Local driver. Same contract as S3, including expiring signed URLs."""

    def __init__(self, root: Path, signing_secret: str, *, base_url: str = "/files") -> None:
        self._root = root
        self._secret = signing_secret.encode("utf-8")
        self._base_url = base_url.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        if ".." in key or key.startswith("/"):
            raise StorageKeyError(f"unsafe key: {key!r}")
        path = (self._root / key).resolve()
        root = self._root.resolve()
        # Belt and braces: even with the checks above, confirm containment.
        if not path.is_relative_to(root):
            raise StorageKeyError(f"key escapes storage root: {key!r}")
        return path

    def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        (path.parent / f"{path.name}.type").write_text(content_type, encoding="utf-8")
        return StoredObject(key=key, size_bytes=len(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)
        (path.parent / f"{path.name}.type").unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    # ── Signing ───────────────────────────────────────────────

    def _signature(self, key: str, expires_at: int) -> str:
        payload = f"{key}:{expires_at}".encode()
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def signed_url(self, key: str, *, ttl_seconds: int) -> str:
        self._resolve(key)  # reject unsafe keys before minting a URL for them
        expires_at = int(time.time()) + ttl_seconds
        query = urlencode({"expires": expires_at, "sig": self._signature(key, expires_at)})
        return f"{self._base_url}/{key}?{query}"

    def verify_signed_url(self, key: str, expires: int, signature: str) -> bool:
        if expires < int(time.time()):
            return False
        return hmac.compare_digest(self._signature(key, expires), signature)
