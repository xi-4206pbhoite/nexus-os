#!/bin/bash
# Creates the application role. Runs once, on first initialisation of the
# data volume.
#
# **This script is the reason Docker does not simply replace db-init.ps1.**
#
# The official Postgres image creates `POSTGRES_USER` as a **superuser**. A
# superuser bypasses row-level security unconditionally — so an application
# connecting as it would sail through every policy in migration 0002, and the
# entire M1 isolation suite would pass while proving nothing.
#
# The app therefore connects as a separate NOSUPERUSER NOBYPASSRLS role, exactly
# as it does against the native cluster. The superuser exists only to own
# extensions and to run migrations.
set -euo pipefail

: "${NEXUS_APP_DB_PASSWORD:?NEXUS_APP_DB_PASSWORD must be set for the app role}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Extensions must be created by a superuser, so they are created here
    -- rather than by the app role inside a migration.
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
    CREATE EXTENSION IF NOT EXISTS vector;

    -- NOSUPERUSER and NOBYPASSRLS are load-bearing, not defaults.
    CREATE ROLE nexus_app WITH
        LOGIN
        NOSUPERUSER
        NOCREATEDB
        NOCREATEROLE
        NOBYPASSRLS
        PASSWORD '${NEXUS_APP_DB_PASSWORD}';

    GRANT ALL ON SCHEMA public TO nexus_app;
    ALTER SCHEMA public OWNER TO nexus_app;
EOSQL

echo "nexus_app created (NOSUPERUSER, NOBYPASSRLS); pgvector installed"
