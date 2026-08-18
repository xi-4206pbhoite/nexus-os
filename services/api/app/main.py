"""FastAPI application entry point."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.config import Env, get_settings
from app.health import router as health_router
from app.jobs.scheduler import build_scheduler
from app.logging import configure_logging, get_logger, request_id_var
from app.routes.auth import router as auth_router
from app.routes.documents import router as documents_router
from app.routes.onboarding import router as onboarding_router
from app.routes.preview import router as preview_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        json_output=settings.env is not Env.local,
        level=logging.DEBUG if settings.debug else logging.INFO,
    )
    log.info("api.startup", env=settings.env.value, embedding_dim=settings.embedding_dim)

    # Only run scheduled work when there is a database to run it against.
    # Starting a sweep that cannot connect would log a failure every hour.
    scheduler = None
    if settings.database_url.get_secret_value():
        scheduler = build_scheduler()
        scheduler.start()
        log.info("scheduler.started", jobs=[j.id for j in scheduler.get_jobs()])

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    log.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NEXUS OS API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_local else None,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach a request id to every log line and response.

        Workspace and user are bound later by the auth dependency (M1) — never
        from a client-supplied header, per doc 06 §2.1.
        """
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(preview_router)
    app.include_router(onboarding_router)
    app.include_router(documents_router)
    return app


app = create_app()
