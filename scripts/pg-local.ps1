# Manages a local, self-contained PostgreSQL cluster for development.
#
# Per ADR 0001 there is no Docker. This uses EnterpriseDB's *binaries ZIP*
# rather than their installer: the installer requires UAC elevation even with
# --extract-only, and registers a Windows service. The ZIP needs neither, so the
# cluster runs as the current user, under our control, and can be deleted by
# removing one directory.
#
# Usage:
#   .\scripts\pg-local.ps1 -Action install -ZipPath <path to binaries zip>
#   .\scripts\pg-local.ps1 -Action start
#   .\scripts\pg-local.ps1 -Action stop
#   .\scripts\pg-local.ps1 -Action status

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install', 'start', 'stop', 'status')]
    [string]$Action,
    [string]$ZipPath,
    [string]$Root = 'D:\PostgreSQL',
    [int]$Port = 5432
)

$ErrorActionPreference = 'Stop'

$BinDir  = Join-Path $Root 'pgsql\bin'
$DataDir = Join-Path $Root 'data'
$LogFile = Join-Path $Root 'postgres.log'
$PwFile  = Join-Path $Root 'superuser.pw'

function Assert-Installed {
    if (-not (Test-Path (Join-Path $BinDir 'pg_ctl.exe'))) {
        Write-Host "PostgreSQL binaries not found at $BinDir." -ForegroundColor Red
        Write-Host "Run: .\scripts\pg-local.ps1 -Action install -ZipPath <binaries zip>" -ForegroundColor Yellow
        exit 1
    }
}

switch ($Action) {

    'install' {
        if (-not $ZipPath -or -not (Test-Path $ZipPath)) {
            Write-Host 'Provide -ZipPath to the EnterpriseDB binaries zip.' -ForegroundColor Red
            exit 1
        }

        New-Item -ItemType Directory -Force -Path $Root | Out-Null

        Write-Host '=== Extracting binaries ===' -ForegroundColor Cyan
        # The zip contains a top-level `pgsql/` directory.
        $7z = 'C:\Program Files\7-Zip\7z.exe'
        if (Test-Path $7z) {
            & $7z x $ZipPath "-o$Root" -y | Select-Object -Last 3
        } else {
            Expand-Archive -Path $ZipPath -DestinationPath $Root -Force
        }
        Assert-Installed
        Write-Host "binaries: $BinDir"

        if (Test-Path (Join-Path $DataDir 'PG_VERSION')) {
            Write-Host 'Data directory already initialised - leaving it alone.' -ForegroundColor Yellow
            break
        }

        Write-Host "`n=== Initialising cluster ===" -ForegroundColor Cyan
        Add-Type -AssemblyName System.Web
        $superPw = ([System.Web.Security.Membership]::GeneratePassword(32, 0)) -replace '[^A-Za-z0-9]', 'x'
        Set-Content -Path $PwFile -Value $superPw -Encoding ascii -NoNewline

        # scram-sha-256 rather than trust: the app connects over TCP as a
        # non-superuser role (see db-init.ps1), and `trust` would make that
        # distinction meaningless.
        & (Join-Path $BinDir 'initdb.exe') `
            -D $DataDir -U postgres --auth-local=scram-sha-256 --auth-host=scram-sha-256 `
            --pwfile=$PwFile --encoding=UTF8 --locale=C 2>&1 | Select-Object -Last 4
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed' }

        # Listen on loopback only. This cluster holds customer data and has no
        # business being reachable from the network.
        Add-Content -Path (Join-Path $DataDir 'postgresql.conf') -Value @"

# NEXUS local development
listen_addresses = '127.0.0.1'
port = $Port
"@
        Write-Host "cluster initialised at $DataDir"
        Write-Host "superuser password: $PwFile (gitignored location)" -ForegroundColor Yellow
    }

    'start' {
        Assert-Installed
        & (Join-Path $BinDir 'pg_ctl.exe') -D $DataDir -l $LogFile -o "-p $Port" start
        Start-Sleep -Seconds 2
        & (Join-Path $BinDir 'pg_isready.exe') -h 127.0.0.1 -p $Port
    }

    'stop' {
        Assert-Installed
        & (Join-Path $BinDir 'pg_ctl.exe') -D $DataDir -m fast stop
    }

    'status' {
        Assert-Installed
        & (Join-Path $BinDir 'pg_ctl.exe') -D $DataDir status
        & (Join-Path $BinDir 'pg_isready.exe') -h 127.0.0.1 -p $Port
    }
}
