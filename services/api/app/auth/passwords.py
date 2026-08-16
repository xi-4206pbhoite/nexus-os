"""Password hashing.

argon2id, the current OWASP recommendation. Parameters are stored inside the
hash string, so raising them later does not invalidate existing hashes —
`needs_rehash` detects the difference and the next successful login upgrades it.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# OWASP's second recommended configuration: 19 MiB, 2 iterations, 1 lane.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

# Long enough to matter, short enough that argon2's memory cost is not a DoS
# vector. Without an upper bound, a multi-megabyte password is a free CPU burn.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024


class WeakPasswordError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time-ish verification. Never raises on a wrong password."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        # A malformed stored hash is a data problem, not an authentication
        # success. Fail closed.
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# A hash of a throwaway value, used to spend comparable time when no user
# exists. Without this, "unknown email" returns measurably faster than "wrong
# password" and the login endpoint becomes a user-enumeration oracle.
DUMMY_HASH = _hasher.hash("nexus-timing-equaliser-not-a-real-password")


def spend_dummy_verification() -> None:
    verify_password(DUMMY_HASH, "wrong")
