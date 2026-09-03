"""No server-side fetch is reachable without a session.

Phase 2 retired the unauthenticated Preview audit and moved its engine into
`app/research/`. Deleting the route removes today's exposure; this test is what
stops tomorrow's from being added by accident.

The rule it enforces is narrow and absolute: **a route that does not require an
authenticated session must not be able to reach `app.research`.** Not "should
not fetch" — must not be able to, checked structurally, because the dangerous
version of this mistake is not a route that crawls on purpose. It is a helper
imported into an unauthenticated module for one innocent function, dragging the
crawler in behind it, and nobody noticing until a stranger is pointing NEXUS at
a company they do not own.

This replaces `test_preview_scope.py`, which asserted the *reduced* shape of the
one unauthenticated audit. That test could only describe the endpoint it was
written for. This one describes every endpoint that will ever exist.

**"Anonymous" here means "declares no session dependency", which is stricter
than "requires no session".** `app/routes/onboarding.py` resolves the session
itself, reading the cookie inside `_require_user` rather than depending on
`CurrentSession`, so three of its four routes are authenticated in fact and
anonymous to any structural check — including this one. That is treated as
anonymous rather than argued away: a check that cannot see an authentication
decision cannot rely on it, and the fix is to declare the dependency.

**The walk is static, over the source, not over `sys.modules`.** A runtime check
sees only what the test session happened to import, and would go quiet exactly
when a new import path was added. An `ast` walk sees the import whether or not
anything calls it.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from fastapi.routing import APIRoute

from app.deps import current_scope, current_session
from app.main import create_app

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# The two dependencies that establish who is calling. `current_session` proves
# an identity; `current_scope` proves an identity *and* a workspace. Either is
# enough to make a route non-anonymous, which is what this file is about.
AUTHENTICATING = frozenset({current_scope, current_session})

# `app.research.ssrf` is the one module in the package an anonymous path may
# import, and the exemption is narrow on purpose: it is the *guard*, not the
# fetch. It resolves a hostname and refuses a private address; importing it is
# never the exposure, and `app/connectors/domain_check.py` — which proves a
# domain claim by fetching a well-known file — is required to use it. Forbidding
# it would push that path towards its own copy of the guard, which is the worst
# available outcome.
#
# Everything else in `app/research/` is off limits: `crawler` performs the
# fetch, and `extract` reads what came back. Neither has any business on a path
# a stranger can reach.
GUARD = "app.research.ssrf"


def _module_name(path: Path) -> str:
    relative = path.relative_to(APP_DIR).with_suffix("")
    parts = [p for p in relative.parts if p != "__init__"]
    return ".".join(["app", *parts])


def _imports_of(path: Path) -> set[str]:
    """Every `app.*` module this file names, whether or not it uses it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not node.module.startswith("app"):
                continue
            found.add(node.module)
            # `from app.research import crawler` names a module in the alias,
            # not in `node.module` — miss this and a package-level import of the
            # crawler reads as an import of the package only.
            found.update(f"{node.module}.{alias.name}" for alias in node.names)

    return found


def _import_graph() -> dict[str, set[str]]:
    return {_module_name(path): _imports_of(path) for path in sorted(APP_DIR.rglob("*.py"))}


def _reachable_from(start: str, graph: dict[str, set[str]]) -> set[str]:
    """Transitive closure, resolving each name to the module that defines it.

    `from app.research.crawler import fetch_page` yields `app.research.crawler`
    directly; `from app.config import Settings` yields `app.config.Settings`,
    which is a symbol rather than a module and is folded back to `app.config`.
    """
    seen: set[str] = set()
    queue = [start]

    while queue:
        current = queue.pop()
        for name in graph.get(current, set()):
            module = name if name in graph else name.rsplit(".", 1)[0]
            if module in graph and module not in seen:
                seen.add(module)
                queue.append(module)

    return seen


def _dependency_calls(dependant: object) -> Iterator[object]:
    call = getattr(dependant, "call", None)
    if call is not None:
        yield call
    for sub in getattr(dependant, "dependencies", []):
        yield from _dependency_calls(sub)


def _served_routes(router: object) -> Iterator[tuple[str, object, object]]:
    """Every route the app actually serves, as (path, endpoint, dependant).

    `include_router` does not flatten in this version of FastAPI — an included
    router appears in `app.routes` as one object holding its own routes, so a
    flat pass over `app.routes` sees three documentation endpoints and nothing
    else. That is exactly the empty set that
    `test_some_routes_are_anonymous_or_this_test_proves_nothing` exists to
    catch, and it caught it.

    The *effective* contexts are used rather than the original routes because
    they carry the dependencies added at include time. A router mounted with
    `dependencies=[Depends(current_scope)]` protects routes whose own
    signatures say nothing about a session, and reading the unresolved route
    would report those as anonymous.
    """
    for route in getattr(router, "routes", []):
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is not None:
            for context in contexts():
                yield context.path, context.endpoint, context.dependant
        elif isinstance(route, APIRoute):
            yield route.path, route.endpoint, route.dependant
        else:
            yield from _served_routes(route)


def _anonymous_route_modules() -> dict[str, list[str]]:
    """Every module defining at least one route that needs no session, and the
    paths that make it so — named, so a failure says which route to look at."""
    anonymous: dict[str, list[str]] = {}

    for path, endpoint, dependant in _served_routes(create_app()):
        if AUTHENTICATING.intersection(_dependency_calls(dependant)):
            continue
        anonymous.setdefault(endpoint.__module__, []).append(path)

    return anonymous


def test_the_research_package_is_where_the_crawler_lives() -> None:
    """Guards the test itself. If `app/research/` were ever renamed away, every
    assertion below would pass by finding nothing, and the file would sit in the
    suite reporting green over an invariant it had stopped checking."""
    graph = _import_graph()

    assert "app.research.crawler" in graph
    assert "app.research.ssrf" in graph
    assert "app.research.extract" in graph


def test_some_routes_are_anonymous_or_this_test_proves_nothing() -> None:
    """The other half of the same guard. Health and sign-in are anonymous by
    design; if the detection above silently classified everything as
    authenticated, the real assertion would be checking an empty set."""
    assert _anonymous_route_modules(), "no anonymous route was detected — the walk is broken"


def test_no_anonymous_route_can_reach_the_crawler() -> None:
    """The invariant.

    Fails if you add `from app.research.crawler import fetch_page` to any route
    module that serves a request without a session — at any depth, through any
    number of intermediate helpers.
    """
    graph = _import_graph()
    offenders: list[str] = []

    for module, paths in sorted(_anonymous_route_modules().items()):
        research = sorted(
            name
            for name in _reachable_from(module, graph)
            if name.startswith("app.research") and name != GUARD
        )
        if research:
            offenders.append(f"{module} (serving {', '.join(sorted(paths))}) reaches {research}")

    assert offenders == [], (
        "an unauthenticated route can reach the crawl engine:\n  "
        + "\n  ".join(offenders)
        + "\nA server-side fetch on an anonymous path lets a stranger point NEXUS "
        "at a company they do not own. Put the route behind CurrentSession."
    )


def test_the_preview_endpoint_is_gone() -> None:
    """The entry point itself, checked through the app rather than by grep.

    A router can be re-registered in `main.py` by anyone restoring a file from
    history, and the import-graph test above would not notice: a resurrected
    `app/routes/preview.py` importing the crawler would be caught, but one
    rebuilt against a different module would not. This asserts the observable
    fact the acceptance test names — nothing answers at `/preview`.
    """
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as client:
        assert client.get("/preview").status_code == 404
        assert client.post("/preview", json={"url": "https://example.com"}).status_code == 404
