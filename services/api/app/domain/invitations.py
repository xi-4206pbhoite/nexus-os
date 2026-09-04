"""Who may invite whom, and to what.

Doc 06 §2.2: *"Every subsequent user's role is set by the inviter, never
self-declared at acceptance. Self-declared role is privilege escalation via
dropdown."* Migration 0006 puts the role on the invitation for that reason, so
acceptance has nothing to supply. This module is the other half of the same
rule: an inviter cannot hand out authority they do not hold.

Three checks, and they are separate because they fail for different reasons:

1. **May this caller invite at all?** Workspace administration is Owner and
   Executive at MVP. No source document names who may invite — see D16 in
   `DECISIONS-REQUIRED.md` — so this is the default-deny reading (I4) rather
   than a settled one, and it is one predicate to widen when it is settled.
2. **Does the invited role exceed the inviter's?** Redundant while (1) admits
   only the two roles that already hold the maximum grant, and written anyway:
   widening (1) later must not silently open an escalation path. The comparison
   is over `ROLE_GRANTS`, so a new role gets the check for free.
3. **May the inviter reach the departments they are assigning?** A Department
   Manager who could invite (should D16 go that way) must not be able to seat
   someone in Finance.

Department assignment itself is derived, not chosen, wherever doc 06 §2.3
derives it: Owner and Executive are `executive` by the table in `scopes.py`, and
the roles that table leaves as `None` are the ones the inviter must fill in.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from app.domain.scopes import DEPARTMENT_BY_ROLE, Department, Role, RoleGrant, Scope, grant_for
from app.domain.session import ScopedSession


class InvitationError(Exception):
    """The invitation as described may not be created."""


def may_administer(role: Role) -> bool:
    """Whether this role may configure the workspace and bring people into it.

    Deliberately expressed against `RoleGrant` rather than as a role list: the
    property that matters is "sees the whole company", and a role added to
    `ROLE_GRANTS` with that property should inherit this without an edit here.
    """
    grant = grant_for(role)
    return grant.all_departments and grant.executive_surface


def outranks(inviter: RoleGrant, invited: RoleGrant) -> bool:
    """Whether `inviter`'s authority covers `invited`'s on every axis.

    Not a single ordering, because the grant is not one-dimensional. A
    Department Manager and a Contributor share a scope ceiling and differ only
    in `contributor_restricted`, so comparing ceilings alone would let a
    Contributor invite a Manager.
    """
    inviter_ceiling = inviter.max_scope or 0
    invited_ceiling = invited.max_scope or 0

    return (
        inviter_ceiling >= invited_ceiling
        and (inviter.all_departments or not invited.all_departments)
        and (inviter.executive_surface or not invited.executive_surface)
        # A restricted caller may only invite an equally restricted one.
        and (not inviter.contributor_restricted or invited.contributor_restricted)
    )


MAX_DEPARTMENTS_PER_MEMBER: Final = 3
"""Q70. Not a technical limit — a person in five departments is not really in
any of them, and the scope lattice stops meaning anything if membership is how
people get broad access rather than the Executive role."""


def departments_for(
    role: Role, requested: Iterable[Department], *, inviter: ScopedSession
) -> frozenset[Department]:
    """The departments to store on the invitation.

    Raises rather than silently correcting. An inviter who names Finance for a
    role that gets `executive` anyway has misunderstood something, and quietly
    storing a different answer than they gave is how a permissions surface stops
    matching what the person who set it believes.
    """
    asked = frozenset(requested)
    derived = DEPARTMENT_BY_ROLE[role]

    if derived is not None:
        # Doc 06 §2.3 — derived from role. Nothing to choose.
        if asked and asked != {derived}:
            raise InvitationError(
                f"A {role.value} is always in {derived.value}; that is not chosen per person."
            )
        return frozenset({derived})

    grant = grant_for(role)

    if grant.max_scope is None or grant.max_scope < Scope.L3_DEPARTMENT:
        # Viewer and External have no L3 at all, so a department would be a
        # label with no effect — and a label with no effect is what someone
        # later mistakes for a boundary.
        if asked:
            raise InvitationError(
                f"A {role.value} has no department access, so no department can be assigned."
            )
        return frozenset()

    if not asked:
        raise InvitationError(f"Choose at least one department for a {role.value}.")

    if len(asked) > MAX_DEPARTMENTS_PER_MEMBER:
        # **Q70 widened this from exactly one.** The previous rule was `!= 1`,
        # and it was too narrow for real companies: a finance lead who also runs
        # operations is ordinary in a fifteen-person business, and forcing them
        # to Executive to describe that gives them the whole company instead.
        #
        # Three, not unlimited: a person in five departments is not really in
        # any of them, and the scope lattice stops meaning anything if
        # membership becomes how people get broad access rather than the
        # Executive role.
        raise InvitationError(
            f"A person can belong to at most {MAX_DEPARTMENTS_PER_MEMBER} departments. "
            "Someone who needs more than that is probably an executive."
        )

    for department in asked:
        if not inviter.may_reach_department(department):
            # Same reasoning as `enforce_department`: naming a department the
            # inviter cannot reach must not confirm that it has anything in it.
            raise InvitationError("Not found")

    return asked


def check_invitation(
    inviter: ScopedSession, *, role: Role, departments: Iterable[Department]
) -> frozenset[Department]:
    """Every precondition for creating an invitation, in one place.

    Returns the departments to store. Raises `InvitationError` otherwise. The
    route calls this and nothing else, so there is one function to audit rather
    than one per check — the same reasoning as `create_workspace_for_claim`.
    """
    if not may_administer(inviter.role) and inviter.role is not Role.DEPARTMENT_MANAGER:
        raise InvitationError(
            "Inviting people is available to owners, executives and department managers."
        )

    if not outranks(grant_for(inviter.role), grant_for(role)):
        raise InvitationError(f"You cannot grant a role above your own: {role.value}.")

    resolved = departments_for(role, departments, inviter=inviter)

    if inviter.role is Role.DEPARTMENT_MANAGER and resolved - inviter.departments:
        # D16/Q68, and this catches only the case `departments_for` cannot.
        #
        # A *named* department the manager cannot reach is already refused
        # there, as "Not found" — deliberately, so the refusal does not confirm
        # the department exists to somebody guessing. That is the better
        # message and it stays.
        #
        # What is left is the **derived** case: a manager inviting an Executive
        # names no department at all, so nothing is outside theirs to check, and
        # then `departments_for` hands back `executive` from the role. The
        # escalation lives in the gap between the request and the derivation,
        # which is why this runs on `resolved` rather than on what was asked.
        raise InvitationError("Not found")

    if len(resolved) > MAX_DEPARTMENTS_PER_MEMBER:
        raise InvitationError(
            f"A person can belong to at most {MAX_DEPARTMENTS_PER_MEMBER} departments. "
            "Someone who needs more than that is probably an executive."
        )

    return resolved
