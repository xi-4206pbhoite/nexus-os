"""Whether a caller may compute something, and what to say when they may not.

**Not in `app/retrieval/`, and that is the point.** It lived there for one
commit and `test_retrieval_signatures` refused it: a `department` parameter
inside the retrieval package is exactly the forgeable-identity shape I2 forbids,
because retrieval must take a `ScopedSession` and derive everything from it.

The guard was right and the location was wrong. This is not retrieval — it reads
nothing and returns no rows. It answers "may this caller compute this capability
at all", which is a question about the *session*, asked before any query runs.

`ARCHITECTURE-LLD.md` §3.2: a calculator whose inputs are not all inside the
caller's scope returns `Locked` rather than computing over what it can see. A
number computed from a subset is **wrong while looking right**, and there is
nothing on the screen to say so.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.scopes import Department, Scope
from app.domain.session import ScopedSession


@dataclass(frozen=True, slots=True)
class Locked:
    """A capability the caller cannot use, and **why** — not a filtered-out row.

    `ARCHITECTURE-LLD.md` §3.2: a calculator whose inputs are not all inside the
    caller's scope returns this rather than computing over what it can see. The
    distinction matters because a number computed from a subset is *wrong* while
    looking right, and there is nothing on the screen to say so.

    It names what would unlock it, because "you cannot see this" that does not
    say what would change it is a dead end the user cannot act on.
    """

    capability: str
    required_source: str | None = None
    required_role: str | None = None

    @property
    def reason(self) -> str:
        if self.required_role:
            return f"{self.capability} needs the {self.required_role} role."
        if self.required_source:
            return f"{self.capability} needs {self.required_source}."
        return f"{self.capability} is not available to you."


def locked_unless_in_scope(
    scope: ScopedSession,
    *,
    capability: str,
    needs: Scope,
    department: Department | None = None,
) -> Locked | None:
    """`None` when the caller may compute this, `Locked` when they may not.

    **Scope level alone is not the test**, and assuming it was is a mistake this
    function made in its first draft. A Contributor's `max_scope` is L3 — the
    same as an Owner's — because the levels say what *kind* of thing a role may
    see, not *which* things. What separates them is which departments they hold
    and whether the executive surface is theirs, so both are checked here.

    Caught by an eval spec that expected a Contributor to be locked out of a
    Finance calculation and found them waved through.
    """
    if not scope.may_reach_scope(needs):
        return Locked(capability=capability, required_role=f"{needs.name.lower()} access")

    if needs is Scope.L4_RESTRICTED and not scope.can_see_executive_surface:
        return Locked(capability=capability, required_role="Owner or Executive")

    if department is not None and department not in scope.departments:
        return Locked(capability=capability, required_role=f"the {department.value} department")

    return None
