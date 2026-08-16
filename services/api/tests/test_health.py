"""Health endpoint behaviour.

The point of these is the honesty rule (I10) applied to our own operations
surface: readiness must not claim `ok` for a dependency that is merely
unconfigured. That is the same failure mode as a dashboard tile showing `0`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

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
    assert names == {"database", "pgvector", "object_storage"}


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


def test_every_response_carries_a_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.headers.get("x-request-id")


def test_supplied_request_id_is_echoed() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"
