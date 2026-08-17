"""Health endpoints.

Split deliberately:

- `/health`   liveness — the process is up. Never touches a dependency, so a
              database outage does not cause a restart loop.
- `/health/ready` readiness — every dependency this service needs is reachable.

Readiness reports each dependency separately rather than a single boolean, so
"the API is down" and "pgvector is not installed on that database" are
distinguishable without reading logs.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])

CheckState = Literal["ok", "degraded", "unconfigured", "error"]


class DependencyCheck(BaseModel):
    name: str
    state: CheckState
    detail: str | None = None
    # False for dependencies a later milestone needs but this one does not.
    # Such a check is still reported — it is simply not allowed to hold the
    # service `not_ready` for work that does not use it (ADR 0004).
    required_now: bool = True


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "nexus-api"


class Readiness(BaseModel):
    status: Literal["ok", "not_ready"]
    env: str
    checks: list[DependencyCheck]


@router.get("/health", response_model=Liveness)
async def liveness() -> Liveness:
    return Liveness()


# Connectivity and the pgvector state in one round trip.
#
# They were two sequential sessions until the database moved to Neon (ADR 0008).
# Each session costs four round trips — pre-ping, BEGIN, the query, ROLLBACK —
# and against a managed database an ocean away that measured 1.8s apiece, making
# readiness a 3.5s call. A probe that slow is indistinguishable from a dead
# service to anything with a timeout, and the web app's 2s budget was already
# reporting the API as unreachable while it was serving perfectly.
#
# Reaching the database at all is what proves connectivity, so the pgvector
# lookup *is* the connectivity check. Both catalogues are queried as scalar
# subqueries: one statement, one answer, no second session.
_DATABASE_PROBE = """
SELECT
    (SELECT count(*) FROM pg_extension WHERE extname = 'vector') AS installed,
    (SELECT count(*) FROM pg_available_extensions WHERE name = 'vector') AS available
"""


async def _probe_database(settings: Settings) -> tuple[DependencyCheck, DependencyCheck]:
    """Both database-backed checks, still reported separately.

    pgvector is not needed until M5, so its absence must not make the service
    `not_ready` for work that does not use it (ADR 0004). But it is the basis of
    I3 — the permission predicate has to be part of the ANN query rather than a
    post-filter — so it must be *visible* from day one rather than discovered
    when indexing starts. A named `unconfigured` state does both.

    Sharing one query does not merge the two verdicts: "the database is
    unreachable" and "the database is fine but has no pgvector" stay distinct
    states, which is the whole point of reporting them apart.
    """
    if not settings.database_url.get_secret_value():
        return (
            DependencyCheck(
                name="database",
                state="unconfigured",
                detail="NEXUS_DATABASE_URL is not set — see .env.example",
            ),
            DependencyCheck(
                name="pgvector",
                state="unconfigured",
                detail="no database configured",
                required_now=False,
            ),
        )

    # Imported here so a missing/invalid URL cannot break module import and take
    # the liveness endpoint down with it.
    from sqlalchemy import text

    from app.db import _unscoped_session

    try:
        async with _unscoped_session() as session:
            row = (await session.execute(text(_DATABASE_PROBE))).one()
    except Exception as exc:
        # A probe reports; it never raises. The exception *type* only — an
        # asyncpg connection error message can contain the DSN, and doc 07 §7
        # forbids secrets reaching the log or response stream.
        #
        # pgvector is reported as an error too, rather than left at
        # `unconfigured`: we did not learn it is missing, we failed to look.
        # Claiming otherwise would turn an outage into a false negative.
        return (
            DependencyCheck(name="database", state="error", detail=type(exc).__name__),
            DependencyCheck(
                name="pgvector",
                state="error",
                detail=f"not determined: {type(exc).__name__}",
                required_now=False,
            ),
        )

    database = DependencyCheck(name="database", state="ok", detail="connected")

    if row.installed:
        vector = DependencyCheck(
            name="pgvector", state="ok", detail="extension installed", required_now=False
        )
    else:
        detail = (
            "available but not created — run migrations"
            if row.available
            else "not available on this server — required from M5 (retrieval)"
        )
        vector = DependencyCheck(
            name="pgvector", state="unconfigured", detail=detail, required_now=False
        )

    return database, vector


def _check_storage(settings: Settings) -> DependencyCheck:
    if settings.storage_backend == "filesystem":
        try:
            settings.storage_root.mkdir(parents=True, exist_ok=True)
            probe = settings.storage_root / ".readiness"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return DependencyCheck(name="object_storage", state="error", detail=str(exc))
        return DependencyCheck(
            name="object_storage", state="ok", detail=f"filesystem:{settings.storage_root.name}"
        )
    return DependencyCheck(name="object_storage", state="unconfigured", detail="s3 not configured")


@router.get("/health/ready", response_model=Readiness)
async def readiness(response: Response) -> Readiness:
    settings = get_settings()
    database, vector = await _probe_database(settings)
    checks = [database, vector, _check_storage(settings)]

    # Advisory checks are reported but do not gate readiness.
    ready = all(c.state == "ok" for c in checks if c.required_now)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return Readiness(status="ok" if ready else "not_ready", env=settings.env.value, checks=checks)
