# Creates the NEXUS database and role on a local PostgreSQL, writes .env, and
# applies migrations. Per ADR 0001 this is the piece `docker compose up` would
# otherwise have done, so it is scripted rather than typed.
#
# Idempotent: safe to re-run. Never overwrites an existing NEXUS_DATABASE_URL.
#
# Usage:  .\scripts\db-init.ps1 -SuperPassword '<postgres superuser password>'

param(
    [Parameter(Mandatory = $true)][string]$SuperPassword,
    [string]$PgHost = '127.0.0.1',
    [int]$Port = 5432,
    [string]$Database = 'nexus',
    [string]$RoleName = 'nexus_app'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# ── Locate psql ─────────────────────────────────────────────
$psql = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $psql) { $psql = Get-Command psql -ErrorAction SilentlyContinue }
if (-not $psql) {
    Write-Host 'psql not found. Install PostgreSQL first.' -ForegroundColor Red
    exit 1
}
$psqlPath = if ($psql.FullName) { $psql.FullName } else { $psql.Source }
Write-Host "psql: $psqlPath"

# ── Generate an application-role password ───────────────────
# The app never connects as superuser: M1 relies on row-level security, and RLS
# is bypassed by roles with BYPASSRLS or superuser. Connecting as `postgres`
# would silently defeat tenant isolation and every test that proves it.
Add-Type -AssemblyName System.Web
$appPassword = ([System.Web.Security.Membership]::GeneratePassword(32, 0)) -replace '[^A-Za-z0-9]', 'x'

$env:PGPASSWORD = $SuperPassword

function Invoke-Psql {
    param([string]$Db, [string]$Sql)
    $out = & $psqlPath -h $PgHost -p $Port -U postgres -d $Db -v ON_ERROR_STOP=1 -tAc $Sql 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $out" }
    return $out
}

Write-Host "`n=== Server reachable? ===" -ForegroundColor Cyan
Invoke-Psql -Db 'postgres' -Sql 'SELECT version();' | Select-Object -First 1

Write-Host "`n=== Role $RoleName ===" -ForegroundColor Cyan
$roleExists = Invoke-Psql -Db 'postgres' -Sql "SELECT 1 FROM pg_roles WHERE rolname='$RoleName';"
if ($roleExists -match '1') {
    Invoke-Psql -Db 'postgres' -Sql "ALTER ROLE $RoleName WITH LOGIN PASSWORD '$appPassword';" | Out-Null
    Write-Host 'exists - password rotated'
} else {
    # NOSUPERUSER / NOBYPASSRLS are load-bearing, not defaults: see above.
    Invoke-Psql -Db 'postgres' -Sql "CREATE ROLE $RoleName WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '$appPassword';" | Out-Null
    Write-Host 'created'
}

Write-Host "`n=== Database $Database ===" -ForegroundColor Cyan
$dbExists = Invoke-Psql -Db 'postgres' -Sql "SELECT 1 FROM pg_database WHERE datname='$Database';"
if ($dbExists -match '1') {
    Write-Host 'exists'
} else {
    Invoke-Psql -Db 'postgres' -Sql "CREATE DATABASE $Database OWNER $RoleName;" | Out-Null
    Write-Host 'created'
}

# Extensions need superuser, so they are created here rather than by the app role.
Invoke-Psql -Db $Database -Sql 'CREATE EXTENSION IF NOT EXISTS pgcrypto;' | Out-Null
$vectorAvailable = Invoke-Psql -Db $Database -Sql "SELECT 1 FROM pg_available_extensions WHERE name='vector';"
if ($vectorAvailable -match '1') {
    Invoke-Psql -Db $Database -Sql 'CREATE EXTENSION IF NOT EXISTS vector;' | Out-Null
    Write-Host 'pgvector: installed' -ForegroundColor Green
} else {
    Write-Host 'pgvector: NOT available - fine until M5 (ADR 0004)' -ForegroundColor Yellow
}

Invoke-Psql -Db $Database -Sql "GRANT ALL ON SCHEMA public TO $RoleName;" | Out-Null
Remove-Item Env:\PGPASSWORD

# ── .env ────────────────────────────────────────────────────
Write-Host "`n=== .env ===" -ForegroundColor Cyan
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $root '.env.example') $envFile }

$url = "postgresql+asyncpg://${RoleName}:${appPassword}@${PgHost}:${Port}/${Database}"
$lines = Get-Content $envFile
$existing = $lines | Where-Object { $_ -match '^NEXUS_DATABASE_URL=' -and $_ -notmatch 'USER:PASSWORD' }
if ($existing) {
    Write-Host 'NEXUS_DATABASE_URL already set - left untouched.' -ForegroundColor Yellow
    Write-Host 'Delete that line and re-run if you want it regenerated.'
} else {
    $lines = $lines | ForEach-Object { if ($_ -match '^NEXUS_DATABASE_URL=') { "NEXUS_DATABASE_URL=$url" } else { $_ } }
    if (-not ($lines -match '^NEXUS_DATABASE_URL=')) { $lines += "NEXUS_DATABASE_URL=$url" }

    # Session and signing secrets, so no secret is left blank or defaulted.
    foreach ($key in @('NEXUS_SESSION_SECRET', 'NEXUS_STORAGE_SIGNING_SECRET')) {
        if (-not ($lines | Where-Object { $_ -match "^$key=.+" })) {
            $secret = ([System.Web.Security.Membership]::GeneratePassword(48, 0)) -replace '[^A-Za-z0-9]', 'x'
            $lines = $lines | ForEach-Object { if ($_ -match "^$key=") { "$key=$secret" } else { $_ } }
        }
    }
    Set-Content -Path $envFile -Value $lines -Encoding utf8
    Write-Host 'written (gitignored)'
}

# ── Migrations ──────────────────────────────────────────────
Write-Host "`n=== Migrations ===" -ForegroundColor Cyan
Push-Location (Join-Path $root 'services\api')
try {
    & .\.venv\Scripts\alembic.exe upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'alembic upgrade failed' }
    & .\.venv\Scripts\alembic.exe current
} finally { Pop-Location }

Write-Host "`nDatabase ready." -ForegroundColor Green
