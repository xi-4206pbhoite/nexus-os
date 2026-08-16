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
    # The real connectivity probe (and the pgvector extension assertion) lands
    # with the database layer in M0.5. Reporting "unconfigured" honestly here is
    # better than reporting "ok" for something not yet wired.
    return DependencyCheck(name="database", state="degraded", detail="probe not yet implemented")


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
    checks = [await _check_database(settings), _check_storage(settings)]

    ready = all(c.state == "ok" for c in checks)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return Readiness(status="ok" if ready else "not_ready", env=settings.env.value, checks=checks)
