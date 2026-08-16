"""Scopes, roles, departments, and the mapping between them.

This is the most important artifact in the security model (doc 06 §2.3). It is
expressed as **data** — a frozen table — rather than as conditionals scattered
through route handlers, because doc 07 M1 requires exactly that and because a
scattered rule cannot be audited or tested as a unit.

Three corrections from doc 06 §2.3 are encoded here, each of which was a bug in
an earlier version of the model:

1. **The lattice is monotonic.** A Viewer previously reached L3 department
   detail while being denied less-sensitive L2. Viewers now get L1 and L2 only.
2. **Contributor is not Manager.** A junior salesperson should not hold every
   deal value in the pipeline, so Contributor's L3 is a restricted subset.
3. **L4 is not reachable by role** — not even by the Owner. It is reachable only
   by being *named* on the item. Otherwise L4 is a UI convention, not a
   boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Scope(IntEnum):
    """Sensitivity lattice. Ordered, so `>=` comparisons are meaningful.

    L0 is deliberately absent: it is the model's parametric knowledge, never
    retrieved content, and therefore never a value on a row. Doc 06 §7.2 is
    explicit that L0 is enforced by prompt and that prompt enforcement is weak —
    representing it here would imply a guarantee the system cannot make.
    """

    L1_COMPANY_PUBLIC = 1
    L2_COMPANY_INTERNAL = 2
    L3_DEPARTMENT = 3
    L4_RESTRICTED = 4
    L5_PERSONAL = 5


class Department(StrEnum):
    MARKETING = "marketing"
    SALES = "sales"
    FINANCE = "finance"
    OPERATIONS = "operations"
    HR = "hr"
    STRATEGY = "strategy"
    EXECUTIVE = "executive"


class Role(StrEnum):
    OWNER = "owner"
    EXECUTIVE = "executive"
    DEPARTMENT_MANAGER = "department_manager"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class RoleGrant:
    """What a role may reach, before any per-user department assignment."""

    max_scope: Scope | None
    """Highest scope reachable by role alone. `None` means nothing at all."""

    all_departments: bool
    """True for roles whose L3 spans every department rather than their own."""

    contributor_restricted: bool
    """Excludes department-wide aggregates and other people's records."""

    executive_surface: bool
    """Chief of Staff page, Morning Brief, composite score."""


# Doc 06 §2.3, verbatim. Changing a row here changes the product's security
# posture, so it is deliberately the only place these facts exist.
ROLE_GRANTS: dict[Role, RoleGrant] = {
    Role.OWNER: RoleGrant(
        max_scope=Scope.L3_DEPARTMENT,
        all_departments=True,
        contributor_restricted=False,
        executive_surface=True,
    ),
    Role.EXECUTIVE: RoleGrant(
        max_scope=Scope.L3_DEPARTMENT,
        all_departments=True,
        contributor_restricted=False,
        executive_surface=True,
    ),
    Role.DEPARTMENT_MANAGER: RoleGrant(
        max_scope=Scope.L3_DEPARTMENT,
        all_departments=False,
        contributor_restricted=False,
        executive_surface=False,
    ),
    Role.CONTRIBUTOR: RoleGrant(
        max_scope=Scope.L3_DEPARTMENT,
        all_departments=False,
        contributor_restricted=True,
        executive_surface=False,
    ),
    Role.VIEWER: RoleGrant(
        # Monotonic: no L3 at all, not "L3 but not L2".
        max_scope=Scope.L2_COMPANY_INTERNAL,
        all_departments=False,
        contributor_restricted=False,
        executive_surface=False,
    ),
    Role.EXTERNAL: RoleGrant(
        max_scope=None,
        all_departments=False,
        contributor_restricted=False,
        executive_surface=False,
    ),
}


# Doc 06 §2.3: "Department is derived from role, not chosen at signup", with the
# Owner able to override per user afterwards.
DEPARTMENT_BY_ROLE: dict[Role, Department | None] = {
    Role.OWNER: Department.EXECUTIVE,
    Role.EXECUTIVE: Department.EXECUTIVE,
    Role.DEPARTMENT_MANAGER: None,  # set explicitly by the inviter
    Role.CONTRIBUTOR: None,
    Role.VIEWER: None,
    Role.EXTERNAL: None,
}


def grant_for(role: Role) -> RoleGrant:
    return ROLE_GRANTS[role]
