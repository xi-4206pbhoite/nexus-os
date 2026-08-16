"""Persona never authorises, and roles are never self-declared.

Two rules from doc 06 that are easy to state and easy to violate later:

- **§2.6** *"No persona field is ever an input to the retrieval predicate.
  Conflating presentation preference with authorisation is how access-control
  bugs get written."* The persona says what to lead with; it must never say
  what may be read.
- **§2.2** *"Every subsequent user's role is set by the inviter, never
  self-declared at acceptance. Self-declared role is privilege escalation via
  dropdown."*
"""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, create_engine, text

from app.domain.session import ScopedSession

REPO_ROOT = Path(__file__).resolve().parents[3]

# Presentation preferences. None of these may appear in `ScopedSession`, which
# is the only thing retrieval consults.
PERSONA_FIELDS = frozenset(
    {
        "stated_purpose",
        "priority_topics",
        "default_landing_screen",
        "communication_style",
        "notification_prefs",
        "language",
        "timezone",
        "seniority",
    }
)


# ── Persona never reaches the predicate ───────────────────────


def test_scoped_session_carries_no_persona_field() -> None:
    """`ScopedSession` is the sole input to every access decision.

    If a persona field appeared here it would be one refactor away from being
    read by a predicate — so the separation is asserted on the type itself.
    """
    fields = set(ScopedSession.__dataclass_fields__)
    leaked = fields & PERSONA_FIELDS
    assert not leaked, f"persona fields must not reach authorisation: {leaked}"


def test_the_access_rule_does_not_reference_persona() -> None:
    """Belt and braces: the rule's source must not mention a preference."""
    from app.domain import access

    source = inspect.getsource(access).lower()
    for field in PERSONA_FIELDS:
        assert field not in source, f"the access rule references persona field {field!r}"


def test_the_scope_table_does_not_reference_persona() -> None:
    from app.domain import scopes

    source = inspect.getsource(scopes).lower()
    for field in PERSONA_FIELDS:
        assert field not in source, f"the scope table references persona field {field!r}"


def test_access_decisions_ignore_everything_but_role_and_department() -> None:
    """Two callers differing only in presentation must decide identically."""
    from app.domain.access import Aggregate, decide_l3_access
    from app.domain.scopes import Department, Role

    common = {
        "tenant_id": uuid4(),
        "workspace_id": uuid4(),
        "role": Role.CONTRIBUTOR,
        "departments": frozenset({Department.SALES}),
    }
    a = ScopedSession(user_id=uuid4(), **common)
    b = ScopedSession(user_id=uuid4(), **common)

    aggregate = Aggregate("sum", Department.SALES)
    assert decide_l3_access(a, aggregate=aggregate) == decide_l3_access(b, aggregate=aggregate)


# ── Invitations ───────────────────────────────────────────────


def _database_url() -> str | None:
    url = os.environ.get("NEXUS_DATABASE_URL") or ""
    if not url:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("NEXUS_DATABASE_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    if not url or "USER:PASSWORD" in url:
        return None
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)


DB_URL = _database_url()
requires_db = pytest.mark.skipif(DB_URL is None, reason="No NEXUS_DATABASE_URL")


@pytest.fixture(scope="module")
def engine():  # type: ignore[no-untyped-def]
    if DB_URL is None:
        pytest.skip("no database")
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine) -> Iterator[Connection]:  # type: ignore[no-untyped-def]
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def workspace(conn: Connection) -> UUID:
    tenant, ws = uuid4(), uuid4()
    conn.execute(text("INSERT INTO tenant (id,name) VALUES (:i,'T')"), {"i": str(tenant)})
    conn.execute(text("SELECT set_config('nexus.workspace_id', :w, true)"), {"w": str(ws)})
    conn.execute(
        text(
            "INSERT INTO workspace (id, workspace_id, tenant_id, name, domain, domain_verified_at)"
            " VALUES (:i,:i,:t,'W',:d, now())"
        ),
        {"i": str(ws), "t": str(tenant), "d": f"inv-{uuid4().hex[:8]}.om"},
    )
    return ws


def user(conn: Connection) -> UUID:
    uid = uuid4()
    conn.execute(
        text("INSERT INTO app_user (id,email) VALUES (:i,:e)"),
        {"i": str(uid), "e": f"i-{uid}@example.com"},
    )
    return uid


@requires_db
def test_the_invitation_carries_the_role_and_who_set_it(conn: Connection) -> None:
    """Doc 06 §2.2 — acceptance copies the role; it never supplies it."""
    ws = workspace(conn)
    inviter = user(conn)

    conn.execute(
        text(
            "INSERT INTO invitation"
            " (workspace_id, email, role, invited_by_user_id, token_hash, expires_at)"
            " VALUES (:w, 'new@acme.om', 'contributor', :u, :h, :x)"
        ),
        {
            "w": str(ws),
            "u": str(inviter),
            "h": uuid4().hex,
            "x": datetime.now(UTC) + timedelta(days=7),
        },
    )

    row = conn.execute(text("SELECT role, invited_by_user_id FROM invitation")).one()
    assert row.role == "contributor"
    assert str(row.invited_by_user_id) == str(inviter)


@requires_db
def test_an_unknown_role_cannot_be_invited(conn: Connection) -> None:
    """A role with no row in the scope table would fall through every check."""
    ws = workspace(conn)
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            text(
                "INSERT INTO invitation (workspace_id, email, role, token_hash, expires_at)"
                " VALUES (:w, 'x@acme.om', 'superadmin', :h, :x)"
            ),
            {"w": str(ws), "h": uuid4().hex, "x": datetime.now(UTC) + timedelta(days=7)},
        )


@requires_db
def test_invitations_are_workspace_isolated(conn: Connection) -> None:
    ws_a = workspace(conn)
    conn.execute(
        text(
            "INSERT INTO invitation (workspace_id, email, role, token_hash, expires_at)"
            " VALUES (:w,'a@acme.om','viewer',:h,:x)"
        ),
        {"w": str(ws_a), "h": uuid4().hex, "x": datetime.now(UTC) + timedelta(days=7)},
    )

    ws_b = workspace(conn)  # sets the GUC to B
    assert conn.execute(text("SELECT count(*) FROM invitation")).scalar() == 0
    assert ws_a != ws_b


# ── Onboarding answers are stored with their scope ────────────


@requires_db
def test_an_l3_answer_must_name_its_department(conn: Connection) -> None:
    """Otherwise it is reachable by anyone holding any L3 access."""
    ws = workspace(conn)
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            text(
                "INSERT INTO onboarding_answer (workspace_id, question_key, value, scope)"
                " VALUES (:w, 'average_deal_size', '\"OMR 4000\"'::jsonb, 'L3')"
            ),
            {"w": str(ws)},
        )


@requires_db
def test_a_scoped_answer_stores_its_classification(conn: Connection) -> None:
    ws = workspace(conn)
    conn.execute(
        text(
            "INSERT INTO onboarding_answer"
            " (workspace_id, question_key, value, scope, department)"
            " VALUES (:w, 'average_deal_size', '\"OMR 4000\"'::jsonb, 'L3', 'sales')"
        ),
        {"w": str(ws)},
    )
    row = conn.execute(
        text(
            "SELECT scope, department FROM onboarding_answer WHERE question_key='average_deal_size'"
        )
    ).one()
    assert row.scope == "L3"
    assert row.department == "sales"


@requires_db
def test_an_unrecognised_scope_cannot_be_stored(conn: Connection) -> None:
    ws = workspace(conn)
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            text(
                "INSERT INTO onboarding_answer (workspace_id, question_key, value, scope)"
                " VALUES (:w, 'x', '\"y\"'::jsonb, 'public')"
            ),
            {"w": str(ws)},
        )
