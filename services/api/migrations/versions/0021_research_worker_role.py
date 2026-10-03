"""Let the worker see the runs it is meant to claim (finding #25).

`research_run` is row-level secured on `nexus.workspace_id`, and **the worker
has no workspace until it claims one** — that is the whole shape of a queue. So
an app-role connection with no GUC set matched no rows, `CLAIM_SQL` returned
nothing forever, and the worker looked perfectly healthy while processing
nothing. No error, no log line, no symptom until somebody asked why research
never runs.

Same shape as finding #18, and the same answer as migration 0015: `nexus_jobs`
exists for maintenance that must span tenants while holding a **narrow policy**
rather than `BYPASSRLS`. Bypass would make every future table silently readable
by this role; a policy per table is a decision each time.

**Write access, unlike 0015's SELECT-only grant, and only here.** A queue worker
that could not update state could not claim anything — `CLAIM_SQL` is an
`UPDATE`. It is still narrow: two tables, no DELETE, and nothing that lets this
role create a run. Queueing belongs to the person who pressed the button.

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                -- SELECT and UPDATE, not INSERT and not DELETE. The worker
                -- claims and finishes runs; it never creates one, because
                -- queueing is the application's job and belongs to the founder
                -- who asked, counted against their allowance (Q55).
                GRANT SELECT, UPDATE ON research_run TO nexus_jobs;
                GRANT SELECT, UPDATE ON research_source TO nexus_jobs;

                CREATE POLICY research_run_worker ON research_run
                    FOR SELECT TO nexus_jobs USING (true);
                CREATE POLICY research_run_worker_claim ON research_run
                    FOR UPDATE TO nexus_jobs USING (true) WITH CHECK (true);

                CREATE POLICY research_source_worker ON research_source
                    FOR SELECT TO nexus_jobs USING (true);
                CREATE POLICY research_source_worker_write ON research_source
                    FOR UPDATE TO nexus_jobs USING (true) WITH CHECK (true);
            ELSE
                RAISE NOTICE
                    'nexus_jobs does not exist - re-run db/bootstrap.sql, or the '
                    'research worker claims nothing and reports no error (finding #25)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs') THEN
                DROP POLICY IF EXISTS research_run_worker ON research_run;
                DROP POLICY IF EXISTS research_run_worker_claim ON research_run;
                DROP POLICY IF EXISTS research_source_worker ON research_source;
                DROP POLICY IF EXISTS research_source_worker_write ON research_source;
                REVOKE ALL ON research_run FROM nexus_jobs;
                REVOKE ALL ON research_source FROM nexus_jobs;
            END IF;
        END $$;
        """
    )
