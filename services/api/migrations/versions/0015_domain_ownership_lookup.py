"""Let the maintenance role answer "is this domain already taken?".

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-03

**Finding #18.** `create_workspace_for_claim` has detected a rival claimant
since M3 with

    SELECT id FROM workspace
     WHERE lower(domain) = :d AND domain_verified_at IS NOT NULL

on an unscoped session. `workspace` carries FORCE ROW LEVEL SECURITY with two
policies — `workspace_id = nexus.workspace_id` (0002) and "a workspace you hold
a membership in" (0008) — and a **second claimant matches neither**. Measured,
not reasoned: the incumbent owner sees the row and a rival sees nothing, with or
without their own `user_id` set.

So the dispute branch has never executed. What held the line is the partial
unique index on `lower(domain) WHERE domain_verified_at IS NOT NULL`, so the
second verification died on a constraint violation and reached the user as a 500
rather than "that company is already here". The data was never wrong; the
handling was never reached.

P5 then reused the same query for its duplicate-domain branch and inherited the
same silence, which is how this was found.

**This extends `nexus_jobs` from one table to two, and ADR 0018 asked for that to
be argued rather than assumed.** The argument:

The *write* half of this exact operation — marking the loser's claim `disputed` —
already runs as `nexus_jobs`, because it too touches a row that is not the
actor's. Leaving the read on the application role while the write sits on the
maintenance role is incoherent: they are one decision split across two
identities, and the half that could see nothing is the half that decided whether
the other ran.

The grant is **SELECT only**, and the application asks one question through it:
does a verified workspace hold this domain. It gets back an id, not a row. A
caller learns that a domain they just typed is taken — precisely what the product
must tell them — and nothing else about the company holding it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                GRANT SELECT ON workspace TO nexus_jobs;
                -- SELECT only, and FOR SELECT rather than a bare policy: this
                -- role must never write a workspace row. Creating a company is
                -- the application's job and belongs to the person doing it.
                CREATE POLICY workspace_ownership_lookup ON workspace
                    FOR SELECT TO nexus_jobs USING (true);
            ELSE
                RAISE NOTICE
                    'nexus_jobs does not exist - re-run db/bootstrap.sql, or the '
                    'duplicate-domain check silently finds nothing (finding #18)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workspace_ownership_lookup ON workspace")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                REVOKE SELECT ON workspace FROM nexus_jobs;
            END IF;
        END $$;
        """
    )
