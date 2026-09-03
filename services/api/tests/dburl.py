"""The test suite's database URL, translated for psycopg2.

Shared because seven test modules had their own copy, and the moment a real
managed Postgres arrived every one of them was wrong in the same way.

**The URL is resolved once, at import.** `conftest.py` pins
`NEXUS_DATABASE_URL` to empty for hermeticity, so a *runtime* read of the
environment sees that blank and falls through to the `.env` fallback below —
which exists on a developer's machine and never in CI. A test calling
`database_url()` inside a test body would therefore get Neon locally and `None`
in CI, on the same code, which is precisely the machine-state dependence this
module was written to remove. Import happens during collection, before any
fixture runs, so the snapshot is the environment as configured.

Two translations, both non-obvious:

- **driver** — the application uses `postgresql+asyncpg://`. These suites are
  synchronous, because they assert *database* behaviour (row-level security)
  rather than application behaviour, and an async harness would only add noise.
- **TLS parameter** — asyncpg takes `ssl`, libpq takes `sslmode`. Neon's own
  connection string says `sslmode=require`, which asyncpg rejects outright with
  `invalid connection option 'sslmode'`; the reverse is equally true for
  psycopg2. So `.env` holds the asyncpg spelling and this converts it back.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve() -> str | None:
    """The URL exactly as configured, in the application's asyncpg spelling.

    Called once, at import. The `.env` fallback is how a local run opts in
    without exporting anything; CI sets the variable instead.
    """
    url = os.environ.get("NEXUS_DATABASE_URL") or ""

    if not url:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("NEXUS_DATABASE_URL="):
                    # .strip() matters: a CRLF .env once put a stray carriage
                    # return inside a database password.
                    url = line.split("=", 1)[1].strip()
                    break

    if not url or "USER:PASSWORD" in url:
        return None
    return url


_CONFIGURED_URL = _resolve()


def async_database_url() -> str | None:
    """The asyncpg DSN, for the few suites that exercise application code paths.

    Most DB tests here are synchronous because they assert database behaviour.
    A test that calls an `async def` in `app/` needs the driver the app uses, and
    must not be handed the psycopg2 translation below — asyncpg rejects
    `sslmode` outright.
    """
    return _CONFIGURED_URL


def database_url() -> str | None:
    """A psycopg2-compatible DSN, or None when no database is configured."""
    url = _CONFIGURED_URL
    if url is None:
        return None

    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)

    # asyncpg's `ssl=` → libpq's `sslmode=`.
    url = re.sub(r"([?&])ssl=", r"\1sslmode=", url)

    return url


def _to_psycopg2(url: str) -> str:
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)
    # asyncpg's `ssl=` → libpq's `sslmode=`.
    return re.sub(r"([?&])ssl=", r"\1sslmode=", url)


_CONFIGURED_JOBS_URL = os.environ.get("NEXUS_JOBS_DATABASE_URL") or None


def jobs_database_url() -> str | None:
    """A psycopg2 DSN for the `nexus_jobs` role, or None when unconfigured.

    ADR 0018. Resolved from the environment only — never from `.env` — because
    the suites that use it assert what that role *cannot* reach, and silently
    falling back to `nexus_app` would make every one of them pass while proving
    the opposite.

    Deliberately not run through `_resolve()`: that has a `.env` fallback which
    exists here and never in CI, and this is exactly the value where that
    divergence would be worst.
    """
    if _CONFIGURED_JOBS_URL is None:
        return None
    return _to_psycopg2(_CONFIGURED_JOBS_URL)
