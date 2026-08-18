"""Provider selection. The one place that decides which implementation runs.

Configuration decides, not the caller. A module that picked its own provider
could pick the live one in a test, or the scripted one in production; both are
the kind of mistake that is invisible until it is expensive.
"""

from __future__ import annotations

from functools import lru_cache

from app.ai.contracts import Availability, LlmProvider, ProviderStatus
from app.ai.providers import UnavailableProvider
from app.config import Settings, get_settings
from app.logging import get_logger

log = get_logger(__name__)


def build_provider(settings: Settings) -> LlmProvider:
    """Choose a provider from configuration.

    Absence of a key is not an error and must never raise here: the application
    is required to start and serve everything else. `UnavailableProvider` is a
    working object that answers honestly, not a null that explodes on use.
    """
    disabled = settings.disabled_ai_skills_set

    if not settings.anthropic_api_key.get_secret_value():
        return UnavailableProvider()

    if settings.ai_enabled is False:
        return UnavailableProvider(
            reason=Availability.DISABLED,
            detail="Language model features are switched off in this environment.",
        )

    # Imported here rather than at module scope so the vendor module is only
    # touched when a key exists. Keeps `import app.main` free of it entirely.
    from app.ai.anthropic_provider import AnthropicProvider

    return AnthropicProvider(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.anthropic_model,
        disabled_skills=disabled,
    )


@lru_cache
def get_provider() -> LlmProvider:
    """The process-wide provider.

    Cached like `get_engine`: constructing one per request would rebuild an HTTP
    client each time. Tests override it via `app.dependency_overrides` or by
    clearing this cache.
    """
    provider = build_provider(get_settings())
    status = provider.status()
    log.info(
        "ai.provider.selected",
        provider=status.provider,
        model=status.model,
        availability=status.availability.value,
    )
    return provider


def provider_status() -> ProviderStatus:
    """For `/health/ready` and any surface that renders AI availability."""
    return get_provider().status()
