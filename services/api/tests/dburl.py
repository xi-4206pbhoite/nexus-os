"""The test suite's database URL, translated for psycopg2.

Shared because seven test modules had their own copy, and the moment a real
managed Postgres arrived every one of them was wrong in the same way.

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


def database_url() -> str | None:
    """A psycopg2-compatible DSN, or None when no database is configured."""
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

    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)

    # asyncpg's `ssl=` → libpq's `sslmode=`.
    url = re.sub(r"([?&])ssl=", r"\1sslmode=", url)

    return url
