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

# The value is passed **raw**, and that is the whole fix.
#
# It used to be pre-quoted — `-v app_password="'${...}'"` — with a comment
# saying psql substitutes `:app_password` literally so the quotes had to be part
# of the value. True of `:app_password`. `bootstrap.sql` uses `:'app_password'`,
# the *auto-quoting* form, so the value was quoted twice and the role's actual
# password became `'ci-app-password'` with the apostrophes in it.
#
# Every symptom pointed away from this: CREATE ROLE succeeded, every NOTICE
# fired, the healthcheck passed, and the first client got "password
# authentication failed" with no clue why. The composed database has never been
# usable by the application — nobody noticed, because nothing had ever tried to
# connect to it until the E2E job did.
# Refuse an empty password rather than create a role nobody can log in as.
#
# `psql -v app_password="''"` is valid SQL and produces a role with an empty
# password — the bootstrap prints CREATE ROLE, every verification NOTICE fires,
# the healthcheck passes, and the first client gets "password authentication
# failed" with nothing anywhere explaining why. Loud beats silent.
for required in NEXUS_APP_DB_PASSWORD; do
  if [ -z "${!required:-}" ]; then
    echo "FATAL: $required is empty. The app role would be created with no" >&2
    echo "password and every client would fail to authenticate." >&2
    exit 1
  fi
done

# `jobs_password` as well as `app_password`. `bootstrap.sql` creates both roles
# and references `:'jobs_password'`, so omitting it fails the whole script on an
# unset variable — which is how the composed database went without the
# `nexus_jobs` role that company registration needs (ADR 0018).
psql -v ON_ERROR_STOP=1 \
     -v app_password="${NEXUS_APP_DB_PASSWORD}" \
     -v jobs_password="${NEXUS_JOBS_DB_PASSWORD:-${NEXUS_APP_DB_PASSWORD}}" \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -f /bootstrap/bootstrap.sql
