# Creates the NEXUS database and role on a local PostgreSQL, writes .env, and
# applies migrations. Per ADR 0001 this is the piece `docker compose up` would
# otherwise have done, so it is scripted rather than typed.
#
# Idempotent: safe to re-run. It will not rotate a password that .env already
# depends on — doing so would leave a valid-looking .env that cannot connect.
#
# Usage:
#   .\scripts\db-init.ps1 -SuperPassword (Get-Content D:\PostgreSQL\superuser.pw)
#   .\scripts\db-init.ps1 -SuperPassword <pw> -Rotate     # force new app password

param(
    [Parameter(Mandatory = $true)][string]$SuperPassword,
    [string]$PgHost = '127.0.0.1',
    [int]$Port = 5432,
    [string]$Database = 'nexus',
    [string]$RoleName = 'nexus_app',
    [switch]$Rotate
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'

Add-Type -AssemblyName System.Web
function New-Secret([int]$Length) {
    ([System.Web.Security.Membership]::GeneratePassword($Length, 0)) -replace '[^A-Za-z0-9]', 'x'
}

# ── Locate psql ─────────────────────────────────────────────
$candidates = @(
    'D:\PostgreSQL\pgsql\bin\psql.exe'
    'C:\Program Files\PostgreSQL\*\bin\psql.exe'
)
$psqlPath = $null
foreach ($c in $candidates) {
    $found = Get-ChildItem $c -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($found) { $psqlPath = $found.FullName; break }
}
if (-not $psqlPath) { $psqlPath = (Get-Command psql -ErrorAction SilentlyContinue).Source }
if (-not $psqlPath) {
    Write-Host 'psql not found. Run: .\scripts\pg-local.ps1 -Action install -ZipPath <zip>' -ForegroundColor Red
    exit 1
}
Write-Host "psql: $psqlPath"

function Invoke-Psql {
    param([string]$Db, [string]$Sql)
    # psql writes NOTICE to stderr, and Windows PowerShell 5.1 wraps a native
    # command's stderr in an ErrorRecord — which $ErrorActionPreference='Stop'
    # turns into a terminating error on a statement that actually succeeded.
    # Relax around the call and branch on the real exit code.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $out = & $psqlPath -h $PgHost -p $Port -U postgres -d $Db -v ON_ERROR_STOP=1 -tAc $Sql 2>&1
    $exit = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($exit -ne 0) { throw "psql failed (exit $exit): $out" }
    return ($out | Where-Object { $_ -notmatch '^(NOTICE|WARNING|INFO):' })
}

# ── Does .env already have a working URL? ───────────────────
$existingUrl = $null
if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match '^NEXUS_DATABASE_URL=.+' -and $_ -notmatch 'USER:PASSWORD' }
    if ($line) { $existingUrl = ($line -split '=', 2)[1] }
}

$env:PGPASSWORD = $SuperPassword

Write-Host "`n=== Server reachable? ===" -ForegroundColor Cyan
(Invoke-Psql -Db 'postgres' -Sql 'SELECT version();') | Select-Object -First 1

# ── Role ────────────────────────────────────────────────────
Write-Host "`n=== Role $RoleName ===" -ForegroundColor Cyan
$roleExists = (Invoke-Psql -Db 'postgres' -Sql "SELECT 1 FROM pg_roles WHERE rolname='$RoleName';") -match '1'

$appPassword = $null
if (-not $roleExists) {
    $appPassword = New-Secret 32
    # NOSUPERUSER / NOBYPASSRLS are load-bearing, not defaults. M1's tenant
    # isolation rests on row-level security, and RLS is bypassed by superuser
    # and BYPASSRLS roles — connecting as postgres would silently defeat both
    # the isolation and every test written to prove it.
    Invoke-Psql -Db 'postgres' -Sql "CREATE ROLE $RoleName WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '$appPassword';" | Out-Null
    Write-Host 'created'
} elseif ($Rotate -or -not $existingUrl) {
    $appPassword = New-Secret 32
    Invoke-Psql -Db 'postgres' -Sql "ALTER ROLE $RoleName WITH LOGIN PASSWORD '$appPassword';" | Out-Null
    Write-Host 'password rotated'
} else {
    Write-Host 'exists - password left alone (.env depends on it; pass -Rotate to force)'
}

# ── Database ────────────────────────────────────────────────
Write-Host "`n=== Database $Database ===" -ForegroundColor Cyan
$dbExists = (Invoke-Psql -Db 'postgres' -Sql "SELECT 1 FROM pg_database WHERE datname='$Database';") -match '1'
if ($dbExists) {
    Write-Host 'exists'
} else {
    Invoke-Psql -Db 'postgres' -Sql "CREATE DATABASE $Database OWNER $RoleName;" | Out-Null
    Write-Host 'created'
}

# Extensions need superuser, so they are created here rather than by the app role.
Invoke-Psql -Db $Database -Sql 'CREATE EXTENSION IF NOT EXISTS pgcrypto;' | Out-Null
$vectorAvailable = (Invoke-Psql -Db $Database -Sql "SELECT 1 FROM pg_available_extensions WHERE name='vector';") -match '1'
if ($vectorAvailable) {
    Invoke-Psql -Db $Database -Sql 'CREATE EXTENSION IF NOT EXISTS vector;' | Out-Null
    Write-Host 'pgvector: installed' -ForegroundColor Green
} else {
    Write-Host 'pgvector: NOT available - fine until M5 (ADR 0004)' -ForegroundColor Yellow
}

Invoke-Psql -Db $Database -Sql "GRANT ALL ON SCHEMA public TO $RoleName;" | Out-Null
Remove-Item Env:\PGPASSWORD

# ── .env ────────────────────────────────────────────────────
Write-Host "`n=== .env ===" -ForegroundColor Cyan
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $root '.env.example') $envFile }
$lines = Get-Content $envFile

if ($appPassword) {
    $url = "postgresql+asyncpg://${RoleName}:${appPassword}@${PgHost}:${Port}/${Database}"
    $lines = $lines | ForEach-Object { if ($_ -match '^NEXUS_DATABASE_URL=') { "NEXUS_DATABASE_URL=$url" } else { $_ } }
    if (-not ($lines -match '^NEXUS_DATABASE_URL=')) { $lines += "NEXUS_DATABASE_URL=$url" }
    Write-Host 'NEXUS_DATABASE_URL written'
} else {
    Write-Host 'NEXUS_DATABASE_URL unchanged'
}

# No secret is left blank or defaulted.
foreach ($key in @('NEXUS_SESSION_SECRET', 'NEXUS_STORAGE_SIGNING_SECRET')) {
    if (-not ($lines | Where-Object { $_ -match "^$key=.+" })) {
        $secret = New-Secret 48
        $lines = $lines | ForEach-Object { if ($_ -match "^$key=") { "$key=$secret" } else { $_ } }
        if (-not ($lines -match "^$key=")) { $lines += "$key=$secret" }
        Write-Host "$key generated"
    }
}
Set-Content -Path $envFile -Value $lines -Encoding utf8

# ── Migrations ──────────────────────────────────────────────
Write-Host "`n=== Migrations ===" -ForegroundColor Cyan
Push-Location (Join-Path $root 'services\api')
try {
    # Same stderr caveat as Invoke-Psql: alembic logs INFO to stderr.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & .\.venv\Scripts\alembic.exe upgrade head 2>&1 | ForEach-Object { "$_" }
    $exit = $LASTEXITCODE
    & .\.venv\Scripts\alembic.exe current 2>&1 | ForEach-Object { "$_" }
    $ErrorActionPreference = $prev
    if ($exit -ne 0) { throw "alembic upgrade failed (exit $exit)" }
} finally { Pop-Location }

Write-Host "`nDatabase ready." -ForegroundColor Green
