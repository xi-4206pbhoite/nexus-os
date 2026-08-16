"""Structured logging.

Doc 07 §7: *no secret in the repo; no customer content in logs.*

Two processors enforce that second rule. `redact_secrets` masks anything whose
key looks like a credential. `block_customer_content` is stricter — it raises
rather than logging, because a log line containing a customer's document text is
a data leak that would otherwise be discovered months later in a log aggregator.
Failing loudly in development is the only way that rule stays true.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
workspace_id_var: ContextVar[str | None] = ContextVar("workspace_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

_SECRET_HINTS = (
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "database_url",
    "dsn",
    "private_key",
    "refresh_token",
    "access_token",
)

# Keys that would carry customer text. These must never be logged at all —
# they belong in `generation.input_snapshot`, which is scope-tagged and
# retention-managed (doc 06 §9), not in an unbounded log stream.
_FORBIDDEN_KEYS = (
    "content",
    "chunk",
    "chunk_text",
    "document_text",
    "page_text",
    "crawled_html",
    "input_snapshot",
    "prompt",
    "completion",
    "message_text",
    "answer",
)

MASK = "***redacted***"


def redact_secrets(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if any(hint in key.lower() for hint in _SECRET_HINTS):
            event_dict[key] = MASK
    return event_dict


def block_customer_content(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in event_dict:
        if key.lower() in _FORBIDDEN_KEYS:
            raise ValueError(
                f"Refusing to log key {key!r}: customer content must never reach the log "
                "stream (doc 07 §7). Log an identifier instead."
            )
    return event_dict


def bind_request_context(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Attach the ambient request identifiers to every line."""
    for name, var in (
        ("request_id", request_id_var),
        ("workspace_id", workspace_id_var),
        ("user_id", user_id_var),
    ):
        value = var.get()
        if value is not None:
            event_dict.setdefault(name, value)
    return event_dict


def configure_logging(*, json_output: bool = True, level: int = logging.INFO) -> None:
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            bind_request_context,
            block_customer_content,
            redact_secrets,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
