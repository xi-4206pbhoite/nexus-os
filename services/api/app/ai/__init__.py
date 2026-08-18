"""The language-model boundary.

Import from `app.ai.contracts` and `app.ai.registry`. Nothing outside this
package imports a vendor SDK, which is what makes the provider swappable and
makes "run the whole product with no API key" a supported state rather than a
degraded one.
"""

from app.ai.contracts import (
    Availability,
    Completion,
    CompletionRequest,
    LlmAuthError,
    LlmError,
    LlmProvider,
    LlmRequestError,
    LlmTransientError,
    LlmUnavailableError,
    Message,
    ProviderStatus,
    Usage,
)
from app.ai.registry import build_provider, get_provider, provider_status

__all__ = [
    "Availability",
    "Completion",
    "CompletionRequest",
    "LlmAuthError",
    "LlmError",
    "LlmProvider",
    "LlmRequestError",
    "LlmTransientError",
    "LlmUnavailableError",
    "Message",
    "ProviderStatus",
    "Usage",
    "build_provider",
    "get_provider",
    "provider_status",
]
