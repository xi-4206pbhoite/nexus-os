"""The Anthropic implementation. The only file that knows the vendor exists.

Isolated deliberately: doc 07's build contract and the D11 decision both leave
open whether a second provider is ever needed, and scattering SDK calls through
the application is what makes that question expensive to answer later.

**The SDK import is lazy and its absence is survivable.** `anthropic` is not
installed until the integration is switched on, and a missing package must not
break `import app.main`. Startup importing this module is not the same as using
it — the health endpoint asks `status()`, which never touches the SDK.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.ai.contracts import (
    Availability,
    Completion,
    CompletionRequest,
    LlmAuthError,
    LlmError,
    LlmRequestError,
    LlmTransientError,
    LlmUnavailableError,
    ProviderStatus,
    Usage,
)
from app.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

log = get_logger(__name__)

PROVIDER_NAME = "anthropic"

# Retried once, and only these. A 4xx is deterministic: the same request gets
# the same rejection and the retry only spends the budget twice.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _sdk() -> Any:
    """Import the SDK on first use, mapping its absence to an auth-style error.

    Not at module scope: `app.main` imports the registry, the registry imports
    this, and a missing optional dependency would then take down an application
    that is meant to run perfectly well without any AI configured at all.
    """
    try:
        import anthropic
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
        raise LlmUnavailableError(
            "the anthropic package is not installed; add it to run with a live provider"
        ) from exc
    return anthropic


def _sdk_importable() -> bool:
    """Whether the optional SDK is present, without importing it.

    `find_spec` rather than a try/import so that `status()` — which a readiness probe
    calls on every request — does not pay for a module import, and does not leave a
    half-imported module behind if one fails.
    """
    from importlib.util import find_spec

    try:
        return find_spec("anthropic") is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


class AnthropicProvider:
    """Talks to Anthropic. Constructed by the registry, never directly."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        disabled_skills: frozenset[str] = frozenset(),
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._disabled_skills = disabled_skills
        self._client: Any | None = None

    # ── Availability ──────────────────────────────────────────

    def status(self) -> ProviderStatus:
        if not self._api_key:
            return ProviderStatus(
                availability=Availability.UNCONFIGURED,
                provider=self.name,
                model=None,
                detail="No API key configured. AI features are unavailable until one is set.",
            )

        # A key is not enough: the SDK is an optional dependency, and it was possible
        # to have one without the other. `/health/ready` then reported the language
        # model as `ok` while any call raised — which is precisely the promise this
        # interface makes and breaks. `contracts.py` says `availability()` answers
        # *before* a call so a surface can render "this needs a key" rather than
        # catching an error from a call it should never have attempted; that only
        # holds if this checks both halves.
        #
        # Found by configuring a key without installing the package, and fixed the
        # same way `app/embedding/fastembed_provider.py` already handled it.
        if not _sdk_importable():
            return ProviderStatus(
                availability=Availability.UNCONFIGURED,
                provider=self.name,
                model=self._model,
                detail=(
                    "An API key is set but the anthropic package is not installed — "
                    'run pip install -e ".[ai]"'
                ),
            )

        return ProviderStatus(
            availability=Availability.AVAILABLE,
            provider=self.name,
            model=self._model,
            detail=f"Configured for {self._model}.",
        )

    def _client_or_raise(self) -> Any:
        if not self._api_key:
            raise LlmUnavailableError("no API key configured")
        if self._client is None:
            self._client = _sdk().AsyncAnthropic(api_key=self._api_key)
        return self._client

    # ── The call ──────────────────────────────────────────────

    async def complete(self, request: CompletionRequest) -> Completion:
        if request.skill in self._disabled_skills:
            raise LlmUnavailableError(f"skill '{request.skill}' is switched off")

        client = self._client_or_raise()
        system = _system_with_grounding(request)
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        started = time.monotonic()
        try:
            response = await self._send(client, request, system, messages)
        except Exception as exc:
            raise _map_error(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        text = _first_text_block(response)
        usage = Usage(
            input_tokens=int(getattr(response.usage, "input_tokens", 0)),
            output_tokens=int(getattr(response.usage, "output_tokens", 0)),
        )
        stop_reason = str(getattr(response, "stop_reason", "") or "unknown")

        # Counts, latency and identifiers only. The prompt and the completion are
        # customer content and belong in the `generation` table under the scope
        # of their inputs, never in a log line.
        log.info(
            "ai.completion",
            skill=request.skill,
            provider=self.name,
            model=self._model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=latency_ms,
            stop_reason=stop_reason,
        )

        return Completion(
            text=text,
            model=str(getattr(response, "model", self._model)),
            provider=self.name,
            usage=usage,
            stop_reason=stop_reason,
            latency_ms=latency_ms,
            truncated=stop_reason == "max_tokens",
        )

    async def _send(
        self,
        client: Any,
        request: CompletionRequest,
        system: str,
        messages: list[dict[str, str]],
    ) -> Any:
        """One retry, transient failures only.

        Deliberately not exponential backoff across many attempts: doc 06 §8's
        pipeline is fetch, compute, one model call, validate, retry once, then
        Unavailable. A request that fails twice should surface as unavailable
        rather than be retried until the budget is gone.
        """
        attempts = 0
        while True:
            attempts += 1
            try:
                return await client.messages.create(
                    model=self._model,
                    system=system,
                    messages=messages,
                    max_tokens=request.max_output_tokens,
                    temperature=request.temperature,
                    timeout=request.timeout_seconds,
                )
            except Exception as exc:
                if attempts >= 2 or not _is_retryable(exc):
                    raise
                log.info("ai.retry", skill=request.skill, provider=self.name)


# ── Helpers ───────────────────────────────────────────────────


def _system_with_grounding(request: CompletionRequest) -> str:
    """Append the pre-computed facts, and forbid inventing more.

    The instruction is not a guarantee — prompt-level rules are weak, which doc
    06 §7.2 says plainly about L0 knowledge. It is the cheap half of the defence.
    The expensive half is M8 validating the response and rejecting figures that
    were not supplied here.
    """
    if not request.grounding:
        return request.system

    facts = "\n".join(f"- {key}: {value!r}" for key, value in sorted(request.grounding.items()))
    return (
        f"{request.system}\n\n"
        "The following values were computed from the company's own data. "
        "Use them exactly as given. Do not calculate, estimate, round or infer "
        "any other figure — if a number you need is not listed here, say which "
        "one is missing instead of producing it.\n\n"
        f"{facts}"
    )


def _first_text_block(response: Any) -> str:
    blocks = getattr(response, "content", None) or []
    parts = [
        str(getattr(block, "text", ""))
        for block in blocks
        if getattr(block, "type", None) == "text"
    ]
    return "".join(parts)


def _status_of(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    return int(value) if isinstance(value, int) else None


def _is_retryable(exc: Exception) -> bool:
    status = _status_of(exc)
    if status is not None:
        return status in _RETRYABLE_STATUS
    # Timeouts and connection resets carry no status. Matching on the class name
    # rather than importing the SDK keeps this file usable when it is absent.
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "TimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
    }


def _map_error(exc: Exception) -> Exception:
    """Vendor exception to ours, so callers never import the SDK to branch."""
    if isinstance(exc, LlmUnavailableError):
        return exc

    status = _status_of(exc)
    if status in {401, 403}:
        return LlmAuthError(f"authentication rejected (HTTP {status})")
    if status is not None and status in _RETRYABLE_STATUS:
        return LlmTransientError(f"provider unavailable (HTTP {status})")
    if status is not None and 400 <= status < 500:
        return LlmRequestError(f"request rejected (HTTP {status})")
    if _is_retryable(exc):
        return LlmTransientError(f"{type(exc).__name__}")

    # Type only. A vendor message can echo the request back, and the request
    # carries customer content.
    return LlmError(f"{type(exc).__name__}")
