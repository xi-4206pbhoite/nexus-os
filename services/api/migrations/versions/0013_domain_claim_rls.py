"""Row-level security on `domain_claim`, with a maintenance role beside it.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-03

`doc/12` §Phase 4 asks for this, and **D24 is why it needed answering first**
(ADR 0018). The predicate is `user_id`-scoped because a claim exists before a
workspace does, so the workspace predicate every other table uses has nothing to
key on.

Written as a bare `user_id` policy it would break two writes, and both would
fail **silently**:

- `jobs/expiry.py:expire_stale_claims` sweeps every user's claims in one
  statement. With no `nexus.user_id` set it would match zero rows and report
  success — abandoned claims accumulating for ever behind a clean log.
- `auth/domains.py` marks the *loser's* claim disputed when a race is lost. The
  actor is the winner; the row is not theirs.

So there are **two policies**, and the second is targeted at a role rather than
at a runtime flag:

    domain_claim_own_rows   TO nexus_app    USING (user_id = nexus.user_id)
    domain_claim_maintenance TO nexus_jobs  USING (true)

`TO role` is the mechanism that makes this a boundary. `nexus_jobs` is
`NOSUPERUSER NOBYPASSRLS` — verified, not assumed, in `db/bootstrap.sql` — and
must authenticate with its own credentials. A GUC-keyed bypass (option A) was
rejected precisely because a GUC is application state, so any code path that can
set one gets everything, and the boundary leaves the database.

**The grant lives here, not in `bootstrap.sql`.** That file runs before any
migration, so `domain_claim` does not exist yet. Keeping the grant beside the
policy also means the two cannot drift.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE domain_claim ENABLE ROW LEVEL SECURITY")
    # FORCE, because the application connects as the table owner and ENABLE
    # alone is inert for an owner — the same trap migration 0002 documents.
    op.execute("ALTER TABLE domain_claim FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY domain_claim_own_rows ON domain_claim
        USING (
            user_id = NULLIF(current_setting('nexus.user_id', true), '')::uuid
        )
        WITH CHECK (
            user_id = NULLIF(current_setting('nexus.user_id', true), '')::uuid
        )
        """
    )

    # Idempotent so a database bootstrapped before ADR 0018 can still migrate:
    # the role may not exist yet on someone's laptop.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                GRANT SELECT, UPDATE ON domain_claim TO nexus_jobs;
                CREATE POLICY domain_claim_maintenance ON domain_claim
                    TO nexus_jobs USING (true) WITH CHECK (true);
            ELSE
                RAISE NOTICE
                    'nexus_jobs does not exist - re-run db/bootstrap.sql, or the '
                    'expiry sweep will silently match zero rows (ADR 0018)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS domain_claim_maintenance ON domain_claim")
    op.execute("DROP POLICY IF EXISTS domain_claim_own_rows ON domain_claim")
    op.execute("ALTER TABLE domain_claim NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE domain_claim DISABLE ROW LEVEL SECURITY")
