"""Session tokens.

The token the browser holds is random and opaque. Only its **hash** is stored,
so a leaked database yields no usable sessions — the same reasoning as password
hashing, applied to the credential that is actually presented on every request.

SHA-256 rather than argon2 here on purpose: the token is 256 bits of CSPRNG
output, so there is nothing to brute-force and no reason to spend argon2's
memory cost on every single request.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

TOKEN_BYTES = 32


def new_token() -> str:
    """A fresh opaque session token, URL-safe."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(stored_hash: str, presented_token: str) -> bool:
    return hmac.compare_digest(stored_hash, hash_token(presented_token))


def new_csrf_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def csrf_matches(expected: str, presented: str | None) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(expected, presented)
