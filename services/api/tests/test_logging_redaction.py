"""Doc 07 §7 — no secret in the repo; no customer content in logs.

These guard M0 task 0.7. They are deliberately written as invariant tests rather
than unit tests: they assert a property of the whole logging pipeline, so they
keep working as processors are added.
"""

from __future__ import annotations

import pytest

from app.logging import MASK, block_customer_content, redact_secrets


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "session_secret",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "apikey",
        "cookie",
        "database_url",
        "oauth_credential",
        "GOOGLE_PRIVATE_KEY",
    ],
)
def test_secret_shaped_keys_are_masked(key: str) -> None:
    out = redact_secrets(None, "info", {key: "hunter2-real-value"})
    assert out[key] == MASK
    assert "hunter2-real-value" not in str(out)


def test_ordinary_keys_survive_redaction() -> None:
    out = redact_secrets(None, "info", {"workspace_id": "ws_1", "duration_ms": 12})
    assert out["workspace_id"] == "ws_1"
    assert out["duration_ms"] == 12


@pytest.mark.parametrize(
    "key",
    [
        "content",
        "chunk_text",
        "document_text",
        "page_text",
        "crawled_html",
        "input_snapshot",
        "prompt",
        "completion",
        "answer",
    ],
)
def test_customer_content_keys_raise_rather_than_log(key: str) -> None:
    """Masking is not enough here.

    A masked field still tells an operator the content existed and invites
    someone to 'temporarily' unmask it. Refusing the log line entirely means the
    mistake is caught in development, not in a log aggregator.
    """
    with pytest.raises(ValueError, match="customer content"):
        block_customer_content(None, "info", {key: "the client's price list says OMR 3,200"})


def test_identifiers_are_still_loggable() -> None:
    """The rule must not make the logs useless — ids are how we debug."""
    event = {"document_id": "doc_42", "chunk_id": "chk_7", "page": 3}
    assert block_customer_content(None, "info", dict(event)) == event
