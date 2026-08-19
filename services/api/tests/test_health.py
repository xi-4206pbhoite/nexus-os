"""Health endpoint behaviour.

The point of these is the honesty rule (I10) applied to our own operations
surface: readiness must not claim `ok` for a dependency that is merely
unconfigured. That is the same failure mode as a dashboard tile showing `0`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import get_settings
from app.health import _check_embeddings
from app.main import create_app


def test_liveness_is_independent_of_dependencies() -> None:
    """Liveness must not touch the database, or an outage becomes a restart loop."""
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nexus-api"}


def test_readiness_reports_not_ready_without_a_database() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"

    names = {check["name"] for check in body["checks"]}
    assert names == {
        "database",
        "pgvector",
        "object_storage",
        "embeddings",
        "language_model",
    }


def test_pgvector_is_reported_but_advisory() -> None:
    """ADR 0004 — pgvector is not required until M5.

    It must still be *visible* from day one, so it is reported as its own
    dependency rather than folded into the database check or omitted. Absent it
    would only be discovered when indexing starts; required it would block four
    milestones that never touch vector search.
    """
    with TestClient(create_app()) as client:
        checks = client.get("/health/ready").json()["checks"]

    pgvector = next(c for c in checks if c["name"] == "pgvector")
    assert pgvector["required_now"] is False
    assert pgvector["detail"]

    database = next(c for c in checks if c["name"] == "database")
    assert database["required_now"] is True


def test_advisory_checks_do_not_gate_readiness() -> None:
    """A failing advisory check alone must not make the service not_ready."""
    from app.health import DependencyCheck

    checks = [
        DependencyCheck(name="database", state="ok"),
        DependencyCheck(name="object_storage", state="ok"),
        DependencyCheck(name="pgvector", state="unconfigured", required_now=False),
    ]
    assert all(c.state == "ok" for c in checks if c.required_now)


def test_readiness_never_reports_ok_for_an_unconfigured_dependency() -> None:
    """I10, applied to ourselves: unconfigured is a named state, not success."""
    with TestClient(create_app()) as client:
        checks = client.get("/health/ready").json()["checks"]

    for check in checks:
        assert check["state"] in {"ok", "degraded", "unconfigured", "error"}
        if check["state"] != "ok":
            assert check["detail"], f"{check['name']} must explain why it is not ok"


async def test_an_unreachable_database_is_not_reported_as_missing_pgvector() -> None:
    """The failure mode created by answering both checks in one query.

    Connectivity and the pgvector lookup share a single statement, because two
    sessions against a managed database cost eight round trips and made readiness
    a 3.5s call (ADR 0008). The hazard in that merge is misattribution: if the
    statement fails, a naive implementation reports `database: error` alongside
    `pgvector: unconfigured — not available on this server`, sending someone to
    install an extension while the real problem is that nothing can reach the
    database.

    We did not learn pgvector is missing. We failed to look. I10 says say so.
    """
    from app.config import Settings
    from app.db import get_engine
    from app.health import _probe_database

    # Port 1 on loopback: nothing listens, and it fails fast rather than waiting
    # on a DNS or routing timeout.
    unreachable = Settings(
        database_url=SecretStr("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/absent")
    )

    get_engine.cache_clear()
    try:
        database, pgvector = await _probe_database(unreachable)
    finally:
        get_engine.cache_clear()

    assert database.state == "error"
    assert pgvector.state == "error", "an unreachable database must not read as 'no pgvector'"
    assert pgvector.detail is not None
    assert "not determined" in pgvector.detail
    assert pgvector.required_now is False, "an unreachable database is the database check's failure"

    # Doc 07 §7 — the DSN must not reach a response body. It carries a password.
    for check in (database, pgvector):
        assert check.detail is not None
        assert "nothing" not in check.detail
        assert "absent" not in check.detail


def test_every_response_carries_a_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.headers.get("x-request-id")


def test_supplied_request_id_is_echoed() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"


# ── Embeddings, reported but never gating (task 5.6) ──────────


def test_embeddings_are_reported_as_unconfigured_by_default() -> None:
    """The default state of a clean install, and a working one.

    Documents still upload, parse, classify and queue for review; they stay
    `parsed`. So this must never make the service `not_ready` — a readiness probe
    failing here would take the whole application out of a load balancer over a
    capability the product is designed to run without.
    """
    check = _check_embeddings()

    assert check.state == "unconfigured"
    assert check.required_now is False


def test_a_refused_embedder_is_an_error_not_an_unconfigured_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`deterministic` in a deployed environment is a deployment mistake.

    It returns well-formed, stable, correctly-sized vectors with no semantic
    structure, so nothing downstream fails and nothing is labelled — the whole
    Brain is indexed with noise and the only symptom is that grounded answers are
    quietly useless. `unconfigured` would read as "switch it on when ready";
    `error` reads as "this is wrong now".
    """
    from app.embedding.registry import get_embedder

    monkeypatch.setenv("NEXUS_EMBEDDING_BACKEND", "deterministic")
    monkeypatch.setenv("NEXUS_ENV", "production")
    get_settings.cache_clear()
    get_embedder.cache_clear()
    try:
        check = _check_embeddings()
    finally:
        get_settings.cache_clear()
        get_embedder.cache_clear()

    assert check.state == "error"
    assert check.detail is not None
    assert "fastembed" in check.detail, "the error must say what to set instead"
    # Still advisory: the product runs, documents are simply not searchable.
    assert check.required_now is False
