-- Database bootstrap: extensions and the application role.
--
-- **Run this once per database, as a superuser, on every environment.**
--   local (container)  : invoked by docker/postgres/init/01-app-role.sh
--   managed Postgres   : run it yourself — there is no initdb hook on RDS,
--                        Cloud SQL, Azure, Supabase or Neon
--
-- It exists as one file precisely because those two paths would otherwise
-- diverge. The properties below are what make row-level security real, and if
-- they were set up by hand in production they could differ from local while
-- every isolation test still passed — the exact "green suite proving nothing"
-- failure the whole schema is designed against.
--
-- Idempotent: safe to re-run against an existing database.
--
-- Usage:
--   psql -v app_password=s3cret -f db/bootstrap.sql -d nexus
--
-- The password is referenced as :'app_password' — psql's quoted-variable form,
-- which escapes it as a SQL literal. Pass the raw value; do not pre-quote it.

\set ON_ERROR_STOP on

-- ── Extensions ───────────────────────────────────────────────
-- Superuser-only on most installations, which is why they are here rather than
-- in a migration (migrations run as the unprivileged app role).
--
-- On a managed provider `vector` may need enabling through the console or a
-- parameter group first. If this line fails, that is why — and it must be
-- resolved rather than skipped: the permission predicate has to be part of the
-- ANN query, not a post-filter (doc 06 §4.4).
CREATE EXTENSION IF NOT EXISTS vector;

-- gen_random_uuid() for primary keys, digest() for content-addressed chunks.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Application role ─────────────────────────────────────────
-- NOSUPERUSER and NOBYPASSRLS are load-bearing, not defaults.
--
-- A superuser, and any role with BYPASSRLS, ignores row-level security
-- unconditionally. The application connecting as such a role would sail through
-- every policy in migration 0002 while the isolation suite passed — which is
-- why `tests/test_tenant_isolation.py` asserts these two flags before anything
-- else, and why that test is worth running against staging as well as locally.
--
-- The official Postgres Docker image makes POSTGRES_USER a superuser, so this
-- separate role is not optional there either.
-- Created via \gexec rather than a DO block, because **psql does not substitute
-- variables inside dollar-quoted strings** — `:app_password` inside `$$ … $$`
-- reaches the server literally and fails with a syntax error. A first version
-- of this file did exactly that: the extensions were created, the role was not,
-- and it would have worked locally forever while breaking on every fresh
-- deployment. `\gexec` runs each returned row as a statement, with substitution
-- happening in the outer query where it works.
SELECT format(
    'CREATE ROLE nexus_app WITH LOGIN NOSUPERUSER NOCREATEDB '
    'NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_app')
\gexec

-- ── The maintenance role (ADR 0018, answering D24) ──────────
--
-- `nexus_jobs` exists so that RLS on `domain_claim` can be `user_id`-scoped
-- without breaking the two writes that legitimately are not one user's: the
-- expiry sweep, which spans every user, and the dispute record, where the actor
-- is the winner of a race and the row belongs to the loser.
--
-- It is **not privileged**. Same flags as `nexus_app`, verified the same way
-- below. What it has is a role-targeted policy on exactly one table (migration
-- 0013), which is a boundary an identity must authenticate to cross rather than
-- a runtime flag any code path can set. That distinction is the whole of D24.
SELECT format(
    'CREATE ROLE nexus_jobs WITH LOGIN NOSUPERUSER NOCREATEDB '
    'NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'jobs_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_jobs')
\gexec

ALTER ROLE nexus_jobs WITH LOGIN NOCREATEDB NOCREATEROLE;
ALTER ROLE nexus_jobs PASSWORD :'jobs_password';

DO $$
BEGIN
    EXECUTE 'ALTER ROLE nexus_jobs WITH NOSUPERUSER NOBYPASSRLS';
    RAISE NOTICE 'nexus_jobs flags asserted directly';
EXCEPTION WHEN insufficient_privilege OR feature_not_supported THEN
    RAISE NOTICE 'cannot ALTER nexus_jobs flags without a superuser - verifying instead';
END $$;

-- Fatal, for the same reason it is fatal for nexus_app. A maintenance role with
-- BYPASSRLS would make ADR 0018 a bypass after all, and the whole point of
-- choosing option B over option A was to avoid that.
DO $$
DECLARE
    is_super boolean;
    bypasses boolean;
BEGIN
    SELECT rolsuper, rolbypassrls INTO is_super, bypasses
      FROM pg_roles WHERE rolname = 'nexus_jobs';

    IF is_super OR bypasses THEN
        RAISE EXCEPTION
            'nexus_jobs has super=% bypassrls=% - either defeats the role-targeted '
            'policy that ADR 0018 rests on, and would make it the GUC bypass that '
            'option A was rejected for', is_super, bypasses;
    END IF;
    RAISE NOTICE 'nexus_jobs verified: NOSUPERUSER, NOBYPASSRLS';
END $$;

-- Flags that any role with CREATEROLE may set.
ALTER ROLE nexus_app WITH LOGIN NOCREATEDB NOCREATEROLE;
ALTER ROLE nexus_app PASSWORD :'app_password';

-- SUPERUSER and BYPASSRLS can only be changed by a superuser — and managed
-- providers do not give you one. Neon refuses even `NOSUPERUSER` with
-- "permission denied to alter role", which aborted an earlier version of this
-- script before it reached the grants below.
--
-- So: try, tolerate the refusal, and then **verify**. Correcting the flags is
-- optional; confirming them is not.
DO $$
BEGIN
    EXECUTE 'ALTER ROLE nexus_app WITH NOSUPERUSER NOBYPASSRLS';
    RAISE NOTICE 'nexus_app flags asserted directly';
EXCEPTION WHEN insufficient_privilege OR feature_not_supported THEN
    RAISE NOTICE 'cannot ALTER these flags without a superuser — verifying instead';
END $$;

-- The verification, and it is fatal. An application role with BYPASSRLS ignores
-- every policy unconditionally: migrations 0002/0003/0006/0007 would be inert,
-- and the whole isolation suite would pass while proving nothing.
--
-- Neon's own `neondb_owner` has bypassrls = true, which is exactly why the
-- application must never connect as it. Failing loudly here is the difference
-- between finding that out now and finding it out from a customer.
DO $$
DECLARE
    is_super boolean;
    is_bypass boolean;
BEGIN
    SELECT rolsuper, rolbypassrls INTO is_super, is_bypass
      FROM pg_roles WHERE rolname = 'nexus_app';

    IF is_super OR is_bypass THEN
        RAISE EXCEPTION
            'nexus_app has super=% bypassrls=% — either bypasses row-level '
            'security entirely. Recreate the role without them, or use a '
            'provider that permits ALTER ROLE ... NOBYPASSRLS.',
            is_super, is_bypass;
    END IF;
    RAISE NOTICE 'nexus_app verified: NOSUPERUSER, NOBYPASSRLS';
END $$;

-- ── Schema access ────────────────────────────────────────────
-- CREATE and USAGE on `public` is all migrations need.
--
-- An earlier comment here claimed the app role must *own* the schema so that
-- FORCE ROW LEVEL SECURITY could be applied. That was wrong: FORCE requires
-- **table** ownership, and the table's owner is whoever created it — which is
-- the role running the migrations. Schema ownership is irrelevant, and on Neon
-- `public` is owned by `pg_database_owner` and stays that way.
GRANT USAGE, CREATE ON SCHEMA public TO nexus_app;

-- Anything already in the schema, for a database that predates this script.
GRANT ALL ON ALL TABLES IN SCHEMA public TO nexus_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO nexus_app;

-- `nexus_jobs` gets USAGE and one table. Deliberately not `ALL TABLES`: a
-- maintenance identity that can reach everything is a second application role,
-- and the argument for it being safe rests on how little it may touch. Adding a
-- table here is a decision, and ADR 0018 puts the burden on whoever adds one to
-- say why the app role cannot do the work.
GRANT USAGE ON SCHEMA public TO nexus_jobs;
-- The table grant is NOT here. `domain_claim` is created by migration 0005 and
-- this file runs before any migration, so granting on it would fail with
-- "relation does not exist" on a fresh database. It lives in migration 0013,
-- beside the policy it goes with — which is the right place anyway: the grant
-- and the policy are one decision and should never be able to drift apart.

-- ── Verification ─────────────────────────────────────────────
-- Printed so a deployment log records what was actually achieved rather than
-- what was intended.
SELECT
    'nexus_app: super=' || rolsuper
    || ' bypassrls=' || rolbypassrls
    || ' (both must be false)' AS role_check
FROM pg_roles WHERE rolname = 'nexus_app';

SELECT 'extensions: ' || string_agg(extname || ' ' || extversion, ', ' ORDER BY extname)
       AS extension_check
FROM pg_extension WHERE extname IN ('vector', 'pgcrypto');
