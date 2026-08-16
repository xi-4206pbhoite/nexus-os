"""The unauthenticated path must not reach a metered API.

Doc 06 §1.2: *"Metered APIs must never sit on an unauthenticated path. In
Preview, PageSpeed and the crawler run under a per-IP and per-domain rate limit
with a global daily ceiling; **DataForSEO, Maps and Custom Search run only after
verification**. Without this, a script exhausts a paid quota and degrades the
product for paying tenants."*

Doc 07 M2's acceptance includes *"confirm no metered API is called"*, and the
natural way to check that — reading the route and seeing no call — stops being
true the moment someone adds an import three modules down. So this walks the
route's actual import graph.

It is written now, while no metered connector exists, precisely so it is already
in place when one is added in M7.
"""

from __future__ import annotations

import importlib
import inspect
from types import ModuleType

import app.routes.preview

# Modules and symbols that cost money per call. Any of these appearing in the
# preview route's transitive imports is the failure this test exists to catch.
METERED_MARKERS = (
    "dataforseo",
    "data_for_seo",
    "custom_search",
    "customsearch",
    "maps_places",
    "places_api",
    "apollo",
    "clearbit",
    "ad_library",
    "openai",
    "anthropic",
    "claude_agent_sdk",
    "voyage",
)


def _transitive_app_imports(root: ModuleType, seen: set[str] | None = None) -> set[str]:
    """Every `app.*` module reachable from `root`."""
    seen = seen if seen is not None else set()
    for value in vars(root).values():
        module = value if isinstance(value, ModuleType) else inspect.getmodule(value)
        name = getattr(module, "__name__", "") if module else ""
        if not name.startswith("app.") or name in seen:
            continue
        seen.add(name)
        _transitive_app_imports(importlib.import_module(name), seen)
    return seen


def test_discovery_actually_walks_the_graph() -> None:
    """Guards against passing vacuously if the walk silently returns nothing."""
    reachable = _transitive_app_imports(app.routes.preview)
    assert "app.connectors.crawler" in reachable
    assert "app.calculators.audit" in reachable


def test_no_metered_connector_is_reachable_from_the_preview_route() -> None:
    reachable = _transitive_app_imports(app.routes.preview)

    offenders = [
        name for name in reachable if any(marker in name.lower() for marker in METERED_MARKERS)
    ]
    assert not offenders, (
        "A metered API is reachable from the unauthenticated Preview path "
        f"(doc 06 §1.2): {offenders}"
    )


def test_no_metered_symbol_is_referenced_in_the_preview_source() -> None:
    """Belt and braces: catches a client constructed inline rather than imported."""
    source = inspect.getsource(app.routes.preview).lower()
    offenders = [marker for marker in METERED_MARKERS if marker in source]
    assert not offenders, f"metered marker in preview route source: {offenders}"


def test_no_model_call_is_reachable_from_preview() -> None:
    """M2 has no model in it at all.

    Every figure the Preview audit shows is computed by pure functions in
    `calculators/` (I1). A model appearing here would not just be a cost
    problem — it would mean a number on the screen came from a language model.
    """
    reachable = _transitive_app_imports(app.routes.preview)
    model_modules = [
        name
        for name in reachable
        if any(m in name.lower() for m in ("anthropic", "openai", "agents", "llm"))
    ]
    assert not model_modules, f"model layer reachable from Preview: {model_modules}"


def test_preview_route_is_unauthenticated_by_design() -> None:
    """It must not require a scope — but that is exactly why the guards exist.

    Stated as a test so that adding auth here (or removing the guards on the
    assumption that auth protects it) is a deliberate, visible change.
    """
    from app.routes.preview import create_preview

    params = inspect.signature(create_preview).parameters
    assert "scope" not in params
    assert "current_scope" not in params
