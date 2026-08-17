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

-- Belt and braces, and the part that matters on a managed instance: if the role
-- already existed with the wrong flags — created by hand, perhaps as a
-- superuser — correct it rather than trusting it.
ALTER ROLE nexus_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE nexus_app PASSWORD :'app_password';

-- ── Schema ownership ─────────────────────────────────────────
-- The app role owns `public` so migrations can create tables and, critically,
-- apply FORCE ROW LEVEL SECURITY — which requires ownership.
--
-- Some managed providers refuse ALTER SCHEMA ... OWNER TO. Where that happens,
-- grant CREATE instead and run migrations as the owning role; the FORCE
-- requirement still has to be satisfied somehow, so verify it afterwards with
-- the query at the bottom of this file.
GRANT ALL ON SCHEMA public TO nexus_app;
DO $$
BEGIN
    EXECUTE 'ALTER SCHEMA public OWNER TO nexus_app';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'could not change owner of schema public — grant retained; '
                 'confirm FORCE ROW LEVEL SECURITY is applied after migrating';
END $$;

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
