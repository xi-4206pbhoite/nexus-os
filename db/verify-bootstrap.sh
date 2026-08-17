#!/bin/bash
# Recreates the database container from an empty volume so the real
# initialisation path runs — the mount, the init hook and bootstrap.sql — then
# asserts the properties that make row-level security real.
#
# Destroys local data. It is only ever test fixtures; migrations recreate the
# schema.
set -uo pipefail
cd /mnt/d/Projects/NEXUS_OS

echo "=== down -v (destroying the volume) ==="
docker compose down -v 2>&1 | tail -3

echo "=== up ==="
docker compose up -d db 2>&1 | tail -3

echo "=== waiting for healthy ==="
for _ in $(seq 1 45); do
  state=$(docker inspect --format '{{.State.Health.Status}}' nexus-db 2>/dev/null || echo missing)
  [ "$state" = "healthy" ] && break
  sleep 4
done
echo "health: ${state:-unknown}"

echo "=== bootstrap.sql output from the init hook ==="
docker logs nexus-db 2>&1 | grep -E 'nexus_app|role_check|extension_check|NOTICE|ERROR|FATAL' | tail -12

echo "=== assertions ==="
docker exec nexus-db psql -U postgres -d nexus -tAc \
  "SELECT 'role super=' || rolsuper || ' bypassrls=' || rolbypassrls FROM pg_roles WHERE rolname='nexus_app'"
docker exec nexus-db psql -U postgres -d nexus -tAc \
  "SELECT 'extensions: ' || string_agg(extname||' '||extversion, ', ' ORDER BY extname) FROM pg_extension WHERE extname IN ('vector','pgcrypto')"
docker exec nexus-db psql -U postgres -d nexus -tAc \
  "SELECT 'public owner: ' || pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'"

echo "=== idempotence: run bootstrap.sql a second time ==="
docker exec -e PGPASSWORD=x nexus-db psql -U postgres -d nexus \
  -v app_password="'rerun-should-not-break'" -f /bootstrap/bootstrap.sql 2>&1 | tail -6
