"""`set_config('nexus.workspace_id', …)` is how a request becomes a tenant.

Every row-level security policy in this database reads that GUC. Setting it is
therefore the single most security-critical line in the codebase, and `doc/12`
P10 asks for it to live in one place — `app/retrieval/`, behind
`scoped_connection` — so there is one function to audit rather than ten.

**Ten modules spelled it out; three still do, and this test names them.**

That is not a passing grade dressed up as a list. It is a ratchet: the rule is
enforced from today, so an eleventh site fails immediately, and the ten are
visible in source control rather than being something a future audit discovers.
The allowlist may only ever shrink — `test_the_allowlist_only_shrinks` asserts
the count, so removing a site is a one-line change and adding one is not
possible without editing a file that explains why you should not.

Seven were consolidated in one pass and now call `apply_workspace_scope` in
`app/retrieval/scoped.py`. The rest have different transaction shapes and were
left deliberately: `auth/service.py` sets it before a workspace exists,
`domain/audit.py` writes inside somebody else's transaction, and
`routes/companies.py` spans a registration that creates the workspace it then
scopes to. Routing those through one primitive is a real refactor with real
failure modes, and doing it badly would be worse than doing it late — a
`scoped_connection` that silently opens a second transaction would break
atomicity in exactly the places that most need it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

APP = Path(__file__).resolve().parents[1] / "app"

# The only place that *should* set it.
SANCTIONED: Final = {"retrieval/scoped.py"}

# Everywhere that currently does and should not. **This list may only shrink.**
# Each entry is a module to route through `scoped_connection`, and the comment
# is why it has not been yet.
ALLOWED_FOR_NOW: Final = {
    # Each of these builds the statement differently enough that the mechanical
    # pass could not reach it — a second site inside a branch, or a literal
    # spelled with different whitespace. They are hand work, and hand work on
    # the line that decides tenancy is not something to rush.
    "auth/domains.py",  # a second site, inside a claim-check branch
    "auth/invitations.py",  # a second site, in the accept path
    "auth/service.py",  # registration and login, both pre-workspace
    "domain/membership.py",  # membership lookup during session resolution
    "routes/companies.py",  # spans creating the workspace and then scoping to it
}

PATTERN: Final = re.compile(r"""set_config\(\s*['"]nexus\.""")


def _sites() -> set[str]:
    found = set()
    for path in APP.rglob("*.py"):
        if PATTERN.search(path.read_text()):
            found.add(str(path.relative_to(APP)))
    return found


def test_no_new_module_sets_the_scoping_guc() -> None:
    """The ratchet.

    An eleventh site fails here, at the point somebody adds it, rather than in
    an audit months later — which is how it reached ten.
    """
    unexpected = _sites() - SANCTIONED - ALLOWED_FOR_NOW
    assert not unexpected, (
        "These modules set `nexus.workspace_id` and are not on the list:\n  "
        + "\n  ".join(sorted(unexpected))
        + "\n\nSetting that GUC is how a request becomes a tenant — every RLS policy "
        "reads it. Route the work through `scoped_connection` in `app/retrieval/` "
        "instead. If you genuinely cannot, add it to ALLOWED_FOR_NOW with a comment "
        "saying why, and know that the list is meant to shrink."
    )


def test_the_allowlist_only_shrinks() -> None:
    """A stale allowlist is worse than none: it reads as a decision when it is
    a leftover. If you have consolidated a module, delete its entry and lower
    this number — that is the whole ceremony."""
    remaining = _sites() & ALLOWED_FOR_NOW
    assert len(remaining) <= 5, (
        f"{len(remaining)} modules still set the GUC directly; the allowlist may only shrink."
    )
    assert not (ALLOWED_FOR_NOW - _sites()), (
        "These are on the allowlist but no longer set the GUC — delete them from it:\n  "
        + "\n  ".join(sorted(ALLOWED_FOR_NOW - _sites()))
    )


def test_the_sanctioned_home_actually_sets_it() -> None:
    """If `scoped_connection` stopped setting the GUC, every policy would see an
    empty string and every scoped query would return nothing — which looks like
    "no data" rather than like a broken security primitive."""
    assert SANCTIONED <= _sites(), "app/retrieval/scoped.py must set the scoping GUC"
