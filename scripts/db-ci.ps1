# Builds the database CI builds, locally, and points this shell at it.
# Run it, then run .\scripts\ci.ps1 in the same window.
#
# Why this exists. Since Phase 0 the suite refuses to report green without a
# real PostgreSQL: ninety-two tests assert database behaviour, row-level
# security above all, and a skipped isolation test proves nothing. So a database
# is now a precondition for running the gate at all, and it has to be one the
# repository can reproduce.
#
# The developer database in .env is a shared Neon instance whose schema drifts
# from the repository - Phase 0 found it five migrations ahead of anything in
# git, with tables no migration here creates. A local run against it proves
# something other than what the repository contains. This script instead builds
# a throwaway database exactly the way .github/workflows/ci.yml does:
#
#   1. the same image CI uses, pgvector/pgvector:pg17 - the native cluster from
#      ADR 0001 has no pgvector, which is the whole reason for ADR 0006, and
#      db\bootstrap.sql fails on its first statement without it
#   2. no volume, and the container is recreated every run, so the schema is
#      only ever what the migrations produce
#   3. db\bootstrap.sql - extensions, and nexus_app as NOSUPERUSER NOBYPASSRLS.
#      The image makes POSTGRES_USER a superuser, and a superuser ignores every
#      policy in migration 0002 while the isolation suite passes
#   4. alembic upgrade head, downgrade base, upgrade head. A downgrade that has
#      never run is a function nobody has called, and the first person to need
#      it will be mid-incident
#   5. $env:NEXUS_DATABASE_URL, for this shell only
#
# Port 55432, not 5432, so it cannot collide with the native cluster or with
# `docker compose up -d db`. It never writes .env - the Neon URL there is left
# exactly as it is.
#
# Usage:
#   .\scripts\db-ci.ps1
#   .\scripts\db-ci.ps1 -Action down
#   .\scripts\db-ci.ps1 -Port 55433

param(
    [ValidateSet('up', 'down')]
    [string]$Action = 'up',
    [int]$Port = 55432,
    [string]$Container = 'nexus-ci-db',
    [string]$Database = 'nexus',
    # Generated per run by default. Supply one to get the same URL back across
    # separate shells - useful when iterating on the suite, since the URL is
    # otherwise only in the shell that built the database.
    [string]$AppPassword,
    # Run the gate straight afterwards, in this session, with the URL set.
    [switch]$RunGate,
    # How long to hold the WSL distribution open. See Start-WslKeepAlive.
    [int]$KeepAliveSeconds = 21600
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

. (Join-Path $PSScriptRoot 'lib\docker.ps1')

$mode = Get-DockerMode
if ($mode -eq 'none') {
    Write-Host 'Docker is not available on Windows or in WSL.' -ForegroundColor Red
    Write-Host 'Docker Engine in WSL needs no UAC (ADR 0007):' -ForegroundColor Yellow
    Write-Host '  wsl -d Ubuntu -u root -- apt-get install -y docker.io docker-compose-v2'
    exit 1
}
Write-Host "docker: $mode"
Start-DockerDaemon

# WSL2 shuts a distribution down once nothing is running in it, and that takes
# the docker daemon and every container with it. Measured, not theoretical: a
# suite run died 90 seconds in with `connection refused` on every remaining
# database test, `wsl -l --running` reported no running distributions, and the
# container was Exited (0) with a fast-shutdown request in its log. Nothing in
# the repository was wrong; the database had simply evaporated mid-run.
#
# A sleeping process is enough to hold the distribution open. Its PID is
# recorded so that a second `up`, or a `down`, does not leak one per run.
$keepAliveFile = Join-Path $env:TEMP "nexus-ci-db.keepalive.pid"

function Stop-WslKeepAlive {
    if (-not (Test-Path $keepAliveFile)) { return }
    $pidText = (Get-Content -Raw -LiteralPath $keepAliveFile).Trim()
    Remove-Item -LiteralPath $keepAliveFile -Force
    $keepAlivePid = 0
    if (-not [int]::TryParse($pidText, [ref]$keepAlivePid)) { return }
    $proc = Get-Process -Id $keepAlivePid -ErrorAction SilentlyContinue
    if ($proc) { Stop-Process -Id $keepAlivePid -Force }
}

function Start-WslKeepAlive {
    Stop-WslKeepAlive
    $proc = Start-Process -FilePath 'wsl.exe' -PassThru -WindowStyle Hidden `
        -ArgumentList @('-d', 'Ubuntu', '--', 'sleep', "$KeepAliveSeconds")
    Set-Content -LiteralPath $keepAliveFile -Value $proc.Id -Encoding ascii
    Write-Host "  holding WSL open for $KeepAliveSeconds s (pid $($proc.Id))"
}

function Remove-CiContainer {
    # Read rather than print: on the first run there is no container, and
    # `docker rm -f` says so on stderr. Shown, that reads like a failure at the
    # top of a run that is fine.
    Get-DockerOutput -Arguments "rm -f $Container" | Out-Null
}

if ($mode -eq 'wsl' -and $Action -eq 'up') { Start-WslKeepAlive }

if ($Action -eq 'down') {
    Remove-CiContainer
    Stop-WslKeepAlive
    Write-Host "removed $Container" -ForegroundColor Green
    exit 0
}

# -- 1. a container with no history --------------------------
Write-Host "`n=== $Container ===" -ForegroundColor Cyan
Remove-CiContainer

Add-Type -AssemblyName System.Web
function New-Secret { ([System.Web.Security.Membership]::GeneratePassword(32, 0)) -replace '[^A-Za-z0-9]', 'x' }
$superPassword = New-Secret
$appPassword = $AppPassword
if (-not $appPassword) { $appPassword = New-Secret }

# db\ is mounted rather than copied, so local and CI provably run the same file.
$dbMount = Convert-ToWslPath (Join-Path $repo 'db')
$run = @(
    "run -d --name $Container"
    # Survives a docker daemon restart. WSL shuts the distro down when idle,
    # and the daemon coming back would otherwise leave the database gone while
    # $env:NEXUS_DATABASE_URL still pointed at it - which reads as every DB test
    # failing to connect for no visible reason. Measured, not theoretical.
    '--restart unless-stopped'
    "-e POSTGRES_PASSWORD=$superPassword"
    "-e POSTGRES_DB=$Database"
    '-e POSTGRES_INITDB_ARGS=--encoding=UTF8'
    "-v ${dbMount}:/bootstrap:ro"
    # No 127.0.0.1 prefix, and that is deliberate. Docker runs inside WSL2
    # (ADR 0007), so a port published to the WSL VM's loopback is reachable
    # from WSL and nowhere else - measured: Windows gets "connection refused",
    # and the suite runs on Windows. Bound to the VM's 0.0.0.0 instead, WSL2's
    # localhost forwarding relays 127.0.0.1:$Port from Windows. WSL2 networking
    # is NAT, so this reaches the host and not the LAN.
    #
    # docker-compose.yml publishes 127.0.0.1:5432:5432 and therefore has the
    # same problem for anything running on Windows.
    "-p ${Port}:5432"
    'pgvector/pgvector:pg17'
) -join ' '
$exit = Invoke-Docker -Arguments $run
if ($exit -ne 0) {
    Write-Host "FAIL  docker run (exit $exit)" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== waiting for postgres ===" -ForegroundColor Cyan
$ready = $false
$deadline = (Get-Date).AddMinutes(2)
while (-not $ready -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $out = Get-DockerOutput -Arguments "exec $Container pg_isready -U postgres -d $Database"
    $last = @($out) | Select-Object -Last 1
    if ($last -match 'accepting connections') { $ready = $true }
}
if (-not $ready) {
    Write-Host 'FAIL  postgres never became ready' -ForegroundColor Red
    Invoke-Docker -Arguments "logs --tail 40 $Container" | Out-Null
    exit 1
}
Write-Host '  accepting connections'

# -- 2. extensions and the unprivileged app role -------------
Write-Host "`n=== bootstrap ===" -ForegroundColor Cyan
$bootstrap = "exec -e PGPASSWORD=$superPassword $Container " +
    "psql -h 127.0.0.1 -U postgres -d $Database " +
    "-v ON_ERROR_STOP=1 -v app_password=$appPassword -f /bootstrap/bootstrap.sql"
$exit = Invoke-Docker -Arguments $bootstrap
if ($exit -ne 0) {
    Write-Host "FAIL  bootstrap.sql (exit $exit)" -ForegroundColor Red
    exit 1
}

$url = "postgresql+asyncpg://nexus_app:$appPassword@127.0.0.1:$Port/$Database"
$env:NEXUS_DATABASE_URL = $url

# -- 3. migrations, both directions --------------------------
Write-Host "`n=== migrations ===" -ForegroundColor Cyan
$alembic = Join-Path $repo 'services\api\.venv\Scripts\alembic.exe'
if (-not (Test-Path $alembic)) {
    Write-Host "No alembic at $alembic -- run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# alembic logs INFO to stderr, and Windows PowerShell 5.1 wraps a native
# command's stderr in an ErrorRecord that $ErrorActionPreference='Stop' turns
# into a terminating error on a command that succeeded. Branch on the exit code.
function Invoke-Alembic {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $alembic @Arguments 2>&1 | ForEach-Object { Write-Host "  $_" }
        $exit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($exit -ne 0) {
        Write-Host "FAIL  alembic $($Arguments -join ' ') (exit $exit)" -ForegroundColor Red
        exit 1
    }
}

Push-Location (Join-Path $repo 'services\api')
try {
    Invoke-Alembic @('upgrade', 'head')
    Invoke-Alembic @('downgrade', 'base')
    Invoke-Alembic @('upgrade', 'head')
} finally {
    Pop-Location
}

# -- 4. what this shell now points at ------------------------
Write-Host ''
Write-Host 'DATABASE READY' -ForegroundColor Green
Write-Host "  $Database in $Container on 127.0.0.1:$Port, as nexus_app"
Write-Host '  $env:NEXUS_DATABASE_URL is set for this shell only. .env is untouched.'
Write-Host '  Next:  .\scripts\ci.ps1'
Write-Host "  WSL is held open for $KeepAliveSeconds s so the container cannot vanish mid-run."
Write-Host "  Done:  .\scripts\db-ci.ps1 -Action down"

if ($RunGate) {
    Write-Host ''
    & (Join-Path $PSScriptRoot 'ci.ps1')
    exit $LASTEXITCODE
}
