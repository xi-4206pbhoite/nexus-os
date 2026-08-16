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
    assert names == {"database", "object_storage"}


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
