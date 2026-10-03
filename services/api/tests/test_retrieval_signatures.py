"""I2, enforced against the source rather than trusted to reviewers.

Doc 06 §4.3: *"If a retrieval tool accepts `user_id` as a parameter, the model
fills it in — and the model's context contains crawled competitor pages and
uploaded PDFs. A single injected line is then sufficient to request another
user's scope."*

A code-review convention does not survive a hurried change at 6pm. This walks
every public callable in `app.retrieval` and fails the build if any of them
accepts an identity or scope argument, or omits `ScopedSession`.

The test is written now, while `retrieval/` holds one function, precisely so it
is already in place when the package grows — the invariant before the feature it
guards (doc 07 §5.3).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterator
from typing import Any

import app.retrieval
from app.domain.session import ScopedSession

# Names that would make scope a caller-supplied value.
FORBIDDEN_PARAMS = frozenset(
    {
        "user_id",
        "userid",
        "uid",
        "workspace_id",
        "workspace",
        "tenant_id",
        "tenant",
        "role",
        "roles",
        "scope",
        "scopes",
        "department",
        "departments",
        "as_user",
        "on_behalf_of",
        "impersonate",
    }
)


def _public_callables() -> Iterator[tuple[str, Any]]:
    package = app.retrieval
    modules = [package]
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        modules.append(importlib.import_module(info.name))

    # The three `apply_*_scope` functions are exempt because they are **the
    # primitives this rule protects**, not something it protects against. They
    # read nothing and return nothing: they set the GUCs every RLS policy
    # consults, so taking an id is their entire purpose, and requiring them to
    # take a `ScopedSession` would be circular — the session is what the GUCs
    # make meaningful in the first place.
    #
    # By exact name so the exemption cannot silently widen. Three is the whole
    # set, one per GUC: workspace, user, invitation token. A **fourth** would
    # mean a new kind of scoping exists, and that is a decision to make
    # deliberately rather than by adding a string here.
    exempt = {"apply_workspace_scope", "apply_user_scope", "apply_invitation_token_scope"}

    seen: set[int] = set()
    for module in modules:
        for name, obj in vars(module).items():
            if name.startswith("_") or name in exempt:
                continue
            if not (inspect.isfunction(obj) or inspect.isasyncgenfunction(obj)):
                continue
            # Only things defined inside the package, not re-exports.
            if not getattr(obj, "__module__", "").startswith("app.retrieval"):
                continue
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            yield f"{module.__name__}.{name}", obj


def test_the_package_actually_exposes_something() -> None:
    """Guards against the suite passing vacuously if discovery breaks."""
    assert list(_public_callables()), "no callables discovered in app.retrieval"


def _is_scoped_session(annotation: Any) -> bool:
    return annotation is ScopedSession or annotation == "ScopedSession"


def test_no_retrieval_function_accepts_an_identity_argument() -> None:
    """A loose identifier is forgeable; a `ScopedSession` is not.

    The rule is not about the parameter's *name* — it is about whether scope
    arrives as data the caller composes. `workspace_id: UUID` is a value a model
    can fill in from an injected instruction. A `ScopedSession` is constructed
    server-side from the session cookie and the membership row, so a parameter
    carrying that type is permitted whatever it is called.
    """
    violations: list[str] = []

    for qualname, func in _public_callables():
        # Unwrap decorators such as @asynccontextmanager.
        target = inspect.unwrap(func)
        for param_name, param in inspect.signature(target).parameters.items():
            if _is_scoped_session(param.annotation):
                continue
            if param_name.lower() in FORBIDDEN_PARAMS:
                violations.append(f"{qualname}({param_name}: {param.annotation})")

    assert not violations, (
        "I2 violation - retrieval takes a query, never a forgeable identity. "
        f"Offending parameters: {violations}"
    )


def _identity_params(func: Any) -> list[str]:
    """The rule under test, applied to one callable."""
    target = inspect.unwrap(func)
    found = []
    for param_name, param in inspect.signature(target).parameters.items():
        if _is_scoped_session(param.annotation):
            continue
        if param_name.lower() in FORBIDDEN_PARAMS:
            found.append(param_name)
    return found


def test_the_guard_catches_a_deliberate_violation() -> None:
    """A guard that cannot fail is not a guard.

    This proves the rule actually rejects the shape doc 06 §4.3 warns about,
    rather than passing because the package happens to be small.
    """
    from uuid import UUID

    def leaky_retrieval(query: str, user_id: UUID) -> None: ...

    def leaky_by_workspace(query: str, workspace_id: UUID) -> None: ...

    def safe_retrieval(caller: ScopedSession, query: str) -> None: ...

    assert _identity_params(leaky_retrieval) == ["user_id"]
    assert _identity_params(leaky_by_workspace) == ["workspace_id"]
    assert _identity_params(safe_retrieval) == []


def test_every_retrieval_function_requires_a_scoped_session() -> None:
    """Scope must be supplied as resolved authority, not as loose identifiers."""
    missing: list[str] = []

    for qualname, func in _public_callables():
        target = inspect.unwrap(func)
        hints = inspect.signature(target).parameters
        takes_scope = any(_is_scoped_session(p.annotation) for p in hints.values())
        if not takes_scope:
            missing.append(qualname)

    assert not missing, (
        "Every retrieval entry point must take a ScopedSession so the permission "
        f"predicate can be part of the query (I3). Missing: {missing}"
    )
