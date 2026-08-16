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


async def _check_database(settings: Settings) -> DependencyCheck:
    if not settings.database_url.get_secret_value():
        return DependencyCheck(
            name="database",
            state="unconfigured",
            detail="NEXUS_DATABASE_URL is not set — see .env.example",
        )

    # Imported here so a missing/invalid URL cannot break module import and take
    # the liveness endpoint down with it.
    from sqlalchemy import text

    from app.db import _unscoped_session

    try:
        async with _unscoped_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        # A probe reports; it never raises. The exception *type* only — an
        # asyncpg connection error message can contain the DSN, and doc 07 §7
        # forbids secrets reaching the log or response stream.
        return DependencyCheck(name="database", state="error", detail=type(exc).__name__)

    return DependencyCheck(name="database", state="ok", detail="connected")


async def _check_pgvector(settings: Settings) -> DependencyCheck:
    """Reported separately from connectivity, on purpose.

    pgvector is not needed until M5, so its absence must not make the service
    `not_ready` for work that does not use it (ADR 0004). But it is the basis of
    I3 — the permission predicate has to be part of the ANN query rather than a
    post-filter — so it must be *visible* from day one rather than discovered
    when indexing starts. A named `unconfigured` state does both.
    """
    if not settings.database_url.get_secret_value():
        return DependencyCheck(
            name="pgvector",
            state="unconfigured",
            detail="no database configured",
            required_now=False,
        )

    from sqlalchemy import text

    from app.db import _unscoped_session

    try:
        async with _unscoped_session() as session:
            installed = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            if installed.first() is not None:
                return DependencyCheck(
                    name="pgvector",
                    state="ok",
                    detail="extension installed",
                    required_now=False,
                )

            available = await session.execute(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
            )
            detail = (
                "available but not created — run migrations"
                if available.first() is not None
                else "not available on this server — required from M5 (retrieval)"
            )
    except Exception as exc:
        return DependencyCheck(
            name="pgvector", state="error", detail=type(exc).__name__, required_now=False
        )

    return DependencyCheck(name="pgvector", state="unconfigured", detail=detail, required_now=False)


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
    checks = [
        await _check_database(settings),
        await _check_pgvector(settings),
        _check_storage(settings),
    ]

    # Advisory checks are reported but do not gate readiness.
    ready = all(c.state == "ok" for c in checks if c.required_now)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return Readiness(status="ok" if ready else "not_ready", env=settings.env.value, checks=checks)
