"""An unhandled exception, correlated and quiet.

Until Phase 1 there was no exception handler at all. Starlette's default turns
an unhandled exception into a bare `Internal Server Error` with no body worth
reading, and the traceback goes to the log with no `x-request-id` attached
because `request_id_var` is only read by the logging processors — which the
default handler never reaches. So a customer reporting "it broke" could not be
matched to a log line, and the only way to find their failure was the timestamp.

Two properties, and they pull in opposite directions:

- the response must carry **enough** to find the log line — the request id, and
  it must be the same one the middleware already put in the header;
- the response must carry **nothing else**. Not the exception type, not its
  message, not a traceback. An error body is the one place a stack trace reaches
  an unauthenticated stranger, and in this product the message could name a
  customer's table, file or column.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app

BOOM = "salaries_2026.xlsx belongs to Contoso and must not appear in a response"


@pytest.fixture
def client() -> Any:
    """The real app, plus one route that raises.

    `raise_server_exceptions=False` so the response can be inspected. With the
    default, TestClient re-raises and there is nothing to assert on — which is
    also why the absence of a handler went unnoticed.
    """
    app: FastAPI = create_app()

    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError(BOOM)

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_an_unhandled_exception_returns_the_request_id(client: TestClient) -> None:
    """The same id in the body and the header, so either one finds the other."""
    response = client.get("/_test/boom", headers={"x-request-id": "known-request-id"})

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "known-request-id"
    assert response.json()["request_id"] == "known-request-id"


def test_the_id_is_generated_when_the_caller_supplies_none(client: TestClient) -> None:
    """Most callers send no header. An uncorrelatable 500 is the default case,
    so it is the one that has to work."""
    response = client.get("/_test/boom")

    generated = response.headers["x-request-id"]
    assert generated
    assert response.json()["request_id"] == generated


def test_the_body_carries_no_customer_content(client: TestClient) -> None:
    """The exception message names a customer's file. None of it may be echoed."""
    response = client.get("/_test/boom")
    body = response.text

    assert "salaries_2026" not in body
    assert "Contoso" not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body
    assert "app/main.py" not in body and "app\\main.py" not in body


def test_the_body_says_something_a_person_can_act_on(client: TestClient) -> None:
    """ "Internal Server Error" tells a user nothing they can do. The request id
    is the one thing that makes a support conversation possible, so the body
    says to quote it."""
    payload = client.get("/_test/boom").json()

    assert set(payload) == {"detail", "request_id"}
    assert "request_id" in payload["detail"] or "reference" in payload["detail"].lower()


def test_the_log_line_carries_the_same_id(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Correlation is only real if both ends have the id.

    The response half is easy to get right and useless alone — an id in the body
    that appears in no log line is a reference number for nothing.

    Asserted on what is actually written to stdout, rather than through
    `structlog.testing.capture_logs`. The application configures its own
    processor chain in `lifespan`, so the capture helper intercepts a chain this
    logger is not using and reports nothing — which would have made this test
    pass or fail for reasons unrelated to the log line. Parsing the emitted JSON
    tests the thing an operator will actually grep.
    """
    response = client.get("/_test/boom", headers={"x-request-id": "correlate-me"})
    assert response.json()["request_id"] == "correlate-me"

    lines = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and "request.unhandled_exception" in line
    ]
    assert lines, "no unhandled-exception log line was emitted"
    assert lines[0]["request_id"] == "correlate-me"
    assert lines[0]["level"] == "error"
    assert "RuntimeError" in lines[0]["exception"], (
        "the traceback belongs in the log, and only in the log"
    )


def test_an_http_exception_is_left_alone(client: TestClient) -> None:
    """The handler must not swallow FastAPI's own error responses.

    A 404 already has a body a caller can use; routing it through a generic
    500 handler would turn every deliberate refusal into an internal error —
    and this product's refusals are load-bearing.
    """
    response = client.get("/documents/review-queue")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
