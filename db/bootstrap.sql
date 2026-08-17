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
