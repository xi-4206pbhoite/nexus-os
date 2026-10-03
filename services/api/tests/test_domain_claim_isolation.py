"""A domain claim belongs to one person, and the database enforces it.

`doc/12` §Phase 4, decided by **D24 / ADR 0018**. Claims exist *before* a
workspace does, so the workspace predicate every other table uses has nothing to
key on — the policy is `user_id`-scoped instead.

Written naively that breaks two writes which are legitimately nobody's in
particular, and **both fail silently**: the expiry sweep spans every user, and
the dispute record is written by the winner of a race about the loser's row. So
there are two policies, and the second is attached to a **role** rather than to a
runtime flag:

    domain_claim_own_rows    TO nexus_app    USING (user_id = nexus.user_id)
    domain_claim_maintenance TO nexus_jobs   USING (true)

The tests below assert both halves. The first is the isolation; the second is
that the escape hatch is real, because a maintenance policy that did not work
would mean the sweep reporting clean passes over rows it never touched — which
is the failure D24 exists to prevent, and it looks exactly like success.

Like `test_tenant_isolation.py`, this drives the **database** with plain SQL as
the real unprivileged roles rather than going through application helpers. The
claim is about the policy, and it should hold whatever the application does.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine

from tests.dburl import database_url, jobs_database_url

DB_URL = database_url()
JOBS_URL = jobs_database_url()
requires_db = pytest.mark.requires_db


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert DB_URL is not None
    eng = create_engine(DB_URL, poolclass=sa.pool.NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    connection = engine.connect()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


def as_user(conn: Connection, user_id: UUID | None) -> None:
    conn.execute(
        sa.text("SELECT set_config('nexus.user_id', :u, true)"),
        {"u": str(user_id) if user_id else ""},
    )


@pytest.fixture
def two_claims(conn: Connection) -> tuple[UUID, UUID, UUID, UUID]:
    """Two people, one claim each."""
    alice, bob = uuid4(), uuid4()
    for user in (alice, bob):
        conn.execute(
            sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
            {"i": str(user), "e": f"claim-{user.hex[:8]}@example.com"},
        )

    claim_a, claim_b = uuid4(), uuid4()
    for claim, user in ((claim_a, alice), (claim_b, bob)):
        as_user(conn, user)
        conn.execute(
            sa.text(
                "INSERT INTO domain_claim"
                " (id, domain, user_id, method, strength, challenge_token, state,"
                "  expires_at)"
                " VALUES (:i,:d,:u,'dns_txt','strong','tok','pending',"
                "         now() + interval '14 days')"
            ),
            {"i": str(claim), "d": f"c-{claim.hex[:8]}.om", "u": str(user)},
        )
    return alice, bob, claim_a, claim_b


@requires_db
def test_a_user_sees_only_their_own_claim(
    conn: Connection, two_claims: tuple[UUID, UUID, UUID, UUID]
) -> None:
    alice, _bob, claim_a, claim_b = two_claims

    as_user(conn, alice)
    visible = {UUID(str(r.id)) for r in conn.execute(sa.text("SELECT id FROM domain_claim")).all()}

    assert claim_a in visible
    assert claim_b not in visible, "another person's domain claim was readable"


@requires_db
def test_an_unidentified_caller_sees_no_claims(
    conn: Connection, two_claims: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """Fails closed. With no GUC the policy matches nothing — which is also why
    `app/auth/domains.py` sets it at both entry points rather than per query."""
    as_user(conn, None)
    assert conn.execute(sa.text("SELECT count(*) FROM domain_claim")).scalar_one() == 0


@requires_db
def test_a_user_cannot_update_somebody_elses_claim(
    conn: Connection, two_claims: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """The half that matters most. Reading someone's claim is a disclosure;
    writing to it is how a domain gets stolen — marking a rival's claim
    `expired` would clear the way for your own."""
    alice, _bob, _claim_a, claim_b = two_claims

    as_user(conn, alice)
    result = conn.execute(
        sa.text("UPDATE domain_claim SET state = 'expired' WHERE id = :i"),
        {"i": str(claim_b)},
    )
    assert result.rowcount == 0, "one user rewrote another user's domain claim"


@requires_db
def test_the_maintenance_role_can_sweep_every_claim(engine: Engine) -> None:
    """ADR 0018's escape hatch, asserted — because if it did not work the
    expiry sweep would match zero rows and report success for ever, and nothing
    would look wrong.

    **This one commits**, unlike every other test here, and that is forced by
    what it checks. `nexus_jobs` connects separately, so it cannot see rows
    sitting in another connection's open transaction — the first version used
    the rolled-back fixture and failed with "cannot see every claim", which was
    perfectly true and had nothing to do with the policy. Rows are cleaned up
    explicitly instead.
    """
    assert JOBS_URL is not None, (
        "NEXUS_JOBS_DATABASE_URL is not configured — the maintenance role is "
        "not optional since ADR 0018"
    )
    alice, bob = uuid4(), uuid4()
    claim_a, claim_b = uuid4(), uuid4()

    with engine.connect() as setup:
        for user, claim in ((alice, claim_a), (bob, claim_b)):
            setup.execute(
                sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
                {"i": str(user), "e": f"sweep-{user.hex[:8]}@example.com"},
            )
            as_user(setup, user)
            setup.execute(
                sa.text(
                    "INSERT INTO domain_claim"
                    " (id, domain, user_id, method, strength, challenge_token, state,"
                    "  expires_at)"
                    " VALUES (:i,:d,:u,'dns_txt','strong','tok','pending',"
                    "         now() + interval '14 days')"
                ),
                {"i": str(claim), "d": f"s-{claim.hex[:8]}.om", "u": str(user)},
            )
        setup.commit()

    try:
        eng = create_engine(JOBS_URL, poolclass=sa.pool.NullPool)
        try:
            with eng.connect() as jobs:
                # No GUC set at all, deliberately: the maintenance policy is
                # keyed on the role, not on anything the caller says about
                # itself.
                visible = {
                    UUID(str(r.id))
                    for r in jobs.execute(sa.text("SELECT id FROM domain_claim")).all()
                }
        finally:
            eng.dispose()

        assert {claim_a, claim_b} <= visible, (
            "nexus_jobs cannot see every claim, so the expiry sweep will match "
            "zero rows and report a clean pass"
        )
    finally:
        with engine.connect() as cleanup:
            for user in (alice, bob):
                as_user(cleanup, user)
                cleanup.execute(
                    sa.text("DELETE FROM domain_claim WHERE user_id = :u"), {"u": str(user)}
                )
                cleanup.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": str(user)})
            cleanup.commit()


@requires_db
def test_the_maintenance_role_is_not_privileged() -> None:
    """The distinction the whole decision rests on. `nexus_jobs` is permitted by
    a policy naming it, not by bypassing policies — option A was rejected
    precisely so this stays true."""
    assert JOBS_URL is not None
    eng = create_engine(JOBS_URL, poolclass=sa.pool.NullPool)
    try:
        with eng.connect() as jobs:
            row = jobs.execute(
                sa.text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'nexus_jobs'")
            ).one()
    finally:
        eng.dispose()

    assert row.rolsuper is False
    assert row.rolbypassrls is False, (
        "nexus_jobs bypasses RLS, which makes ADR 0018 the bypass it rejected"
    )


@requires_db
def test_the_maintenance_role_cannot_reach_customer_data() -> None:
    """Its access is one table wide, and that is what makes it defensible.

    A maintenance identity that could read `document` or `chunk` would be a
    second application role with none of the scoping — so the grant is asserted
    to be as narrow as `db/bootstrap.sql` and migration 0013 claim.
    """
    assert JOBS_URL is not None
    eng = create_engine(JOBS_URL, poolclass=sa.pool.NullPool)
    try:
        with eng.connect() as jobs:
            for table in ("document", "chunk", "app_user", "membership"):
                with pytest.raises(Exception, match="permission denied"):
                    # The table names are the literal tuple above, not input.
                    # A bind parameter cannot name a relation, so interpolation
                    # is the only way to vary an identifier.
                    jobs.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1"))  # noqa: S608
                jobs.rollback()
    finally:
        eng.dispose()


# ── One live attempt per person per domain (F12) ──────────────


@requires_db
def test_only_one_claim_per_domain_per_person_can_be_pending(conn: Connection) -> None:
    """Finding F12, asserted at the database rather than at the route.

    The E2E pass reported four simultaneous `pending` claims on one domain for
    one account, one per method. Two separate mechanisms in this repository say
    that cannot happen: `start_claim` expires any live attempt on the same
    domain before inserting, and migration 0005 carries a partial unique index
    on `(lower(domain), user_id) WHERE state = 'pending'`.

    Neither was covered by a test, which is the part worth fixing whatever the
    report saw. A schema that has drifted from its migrations is a documented
    hazard here — the D23 incident found the Neon instance five migrations
    ahead of the repository — and *"a run against a drifted database can pass a
    defect the repository still has"* cuts both ways. This is what says so.
    """
    user = uuid4()
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"dedupe-{user.hex[:8]}@example.com"},
    )
    as_user(conn, user)

    domain = f"dedupe-{user.hex[:8]}.om"

    def insert(method: str) -> None:
        conn.execute(
            sa.text(
                "INSERT INTO domain_claim"
                " (id, domain, user_id, method, strength, challenge_token, state,"
                "  expires_at)"
                " VALUES (:i,:d,:u,:m,'strong',:t,'pending',"
                "         now() + interval '14 days')"
            ),
            {
                "i": str(uuid4()),
                "d": domain,
                "u": str(user),
                "m": method,
                "t": f"tok-{method}",
            },
        )

    insert("dns_txt")

    # A second live attempt on the same domain, by the same person, whatever
    # method it names. The index does not mention `method` on purpose: offering
    # a claim per method is reasonable, four valid challenge tokens at once is
    # not.
    with pytest.raises(sa.exc.IntegrityError):
        insert("file")


@requires_db
def test_starting_a_second_claim_replaces_the_first_rather_than_failing(
    conn: Connection,
) -> None:
    """The other side of it: retrying must still work.

    The index above would be a trap on its own — a person who starts a DNS
    claim and then decides to publish a file instead would hit a constraint
    violation. `start_claim` expires the live attempt first, so the second
    method is offered and the first token stops being valid. Both halves are
    needed, and only together do they mean *"one live attempt, and you may
    change your mind"*.
    """
    user = uuid4()
    conn.execute(
        sa.text("INSERT INTO app_user (id, email) VALUES (:i,:e)"),
        {"i": str(user), "e": f"replace-{user.hex[:8]}@example.com"},
    )
    as_user(conn, user)

    domain = f"replace-{user.hex[:8]}.om"

    def start(method: str) -> None:
        # The same two statements `start_claim` issues, in the same order.
        conn.execute(
            sa.text(
                "UPDATE domain_claim SET state = 'expired'"
                " WHERE lower(domain) = :d AND user_id = :u AND state = 'pending'"
            ),
            {"d": domain, "u": str(user)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO domain_claim"
                " (id, domain, user_id, method, strength, challenge_token, state,"
                "  expires_at)"
                " VALUES (:i,:d,:u,:m,'strong',:t,'pending',"
                "         now() + interval '14 days')"
            ),
            {
                "i": str(uuid4()),
                "d": domain,
                "u": str(user),
                "m": method,
                "t": f"tok-{method}",
            },
        )

    for method in ("dns_txt", "file", "email", "manual"):
        start(method)

    live = (
        conn.execute(
            sa.text(
                "SELECT method FROM domain_claim"
                " WHERE lower(domain) = :d AND user_id = :u AND state = 'pending'"
            ),
            {"d": domain, "u": str(user)},
        )
        .scalars()
        .all()
    )

    assert live == ["manual"], f"expected one live claim, found {live}"
