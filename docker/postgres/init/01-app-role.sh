#!/bin/bash
# Runs the shared bootstrap on first initialisation of the data volume.
#
# This script is deliberately thin. All the SQL lives in `db/bootstrap.sql`,
# which a managed Postgres runs **by hand** at deployment — there is no
# `docker-entrypoint-initdb.d` hook on RDS, Cloud SQL, Azure, Supabase or Neon.
#
# Keeping the SQL in one file is the point. The role flags it sets are what make
# row-level security real, and if local and production set them up separately
# they could differ while every isolation test still passed.
set -euo pipefail

: "${NEXUS_APP_DB_PASSWORD:?NEXUS_APP_DB_PASSWORD must be set for the app role}"

# The value is quoted twice on purpose: psql substitutes :app_password
# literally, so the SQL string quotes must be part of the variable itself.
psql -v ON_ERROR_STOP=1 \
     -v app_password="'${NEXUS_APP_DB_PASSWORD}'" \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -f /bootstrap/bootstrap.sql
