# Brings up the Dockerised database (ADR 0006) and points .env at it.
#
# Replaces pg-local.ps1 + db-init.ps1 once Docker is available. The native
# cluster stays installed as a fallback; whichever is running on 5432 is the
# one .env resolves to, so only the credentials differ.
#
# Usage:
#   .\scripts\db-docker.ps1 -Action up
#   .\scripts\db-docker.ps1 -Action down
#   .\scripts\db-docker.ps1 -Action status
#   .\scripts\db-docker.ps1 -Action reset    # destroys the volume

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('up', 'down', 'status', 'reset')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

. (Join-Path $PSScriptRoot 'lib\docker.ps1')

$mode = Get-DockerMode
if ($mode -eq 'none') {
    Write-Host 'Docker is not available on Windows or in WSL.' -ForegroundColor Red
    Write-Host 'Docker Engine in WSL needs no UAC (ADR 0007):' -ForegroundColor Yellow
    Write-Host '  wsl -d Ubuntu -u root -- apt-get install -y docker.io docker-compose-v2'
    Write-Host 'The native cluster also still works: .\scripts\pg-local.ps1 -Action start'
    exit 1
}
Write-Host "docker: $mode"
Start-DockerDaemon

Add-Type -AssemblyName System.Web
function New-Secret { ([System.Web.Security.Membership]::GeneratePassword(32, 0)) -replace '[^A-Za-z0-9]', 'x' }

$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $root '.env.example') $envFile }
$lines = [System.Collections.ArrayList](Get-Content $envFile)

function Set-EnvValue([string]$Key, [string]$Value) {
    $existing = $lines | Where-Object { $_ -match "^$Key=.+" }
    if ($existing) { return ($existing -split '=', 2)[1] }
    $idx = 0; $replaced = $false
    foreach ($line in $lines) {
        if ($line -match "^$Key=") { $lines[$idx] = "$Key=$Value"; $replaced = $true; break }
        $idx++
    }
    if (-not $replaced) { [void]$lines.Add("$Key=$Value") }
    return $Value
}

switch ($Action) {

    'up' {
        # Generated once and then left alone: the volume stores a hash of the
        # password from first initialisation, so rotating it here without
        # resetting the volume would break the connection.
        $superPw = Set-EnvValue 'NEXUS_DB_SUPERUSER_PASSWORD' (New-Secret)
        $appPw = Set-EnvValue 'NEXUS_APP_DB_PASSWORD' (New-Secret)
        Set-Content -Path $envFile -Value $lines -Encoding utf8

        Write-Host '=== Starting the database ===' -ForegroundColor Cyan
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $exit = Invoke-Docker -Arguments 'compose up -d db' -WorkingDirectory $root
        $ErrorActionPreference = $previous
        if ($exit -ne 0) { throw "docker compose failed (exit $exit)" }

        Write-Host "`n=== Waiting for pgvector ===" -ForegroundColor Cyan
        # Waits on the healthcheck, which asserts the extension exists rather
        # than merely that Postgres answers.
        $deadline = (Get-Date).AddMinutes(3)
        do {
            Start-Sleep -Seconds 3
            $state = Get-DockerContainerHealth
            Write-Host "  $state"
        } while ($state -ne 'healthy' -and (Get-Date) -lt $deadline)

        if ($state -ne 'healthy') { throw "database did not become healthy: $state" }

        # Same DSN shape as the native cluster - only the credentials differ.
        $url = "postgresql+asyncpg://nexus_app:$appPw@127.0.0.1:5432/nexus"
        $idx = 0
        foreach ($line in $lines) {
            if ($line -match '^NEXUS_DATABASE_URL=') { $lines[$idx] = "NEXUS_DATABASE_URL=$url" }
            $idx++
        }
        foreach ($key in @('NEXUS_SESSION_SECRET', 'NEXUS_STORAGE_SIGNING_SECRET')) {
            if (-not ($lines | Where-Object { $_ -match "^$key=.+" })) {
                $i = 0
                foreach ($line in $lines) {
                    if ($line -match "^$key=") { $lines[$i] = "$key=$(New-Secret)" }
                    $i++
                }
            }
        }
        Set-Content -Path $envFile -Value $lines -Encoding utf8
        Write-Host '.env points at the container.' -ForegroundColor Green

        Write-Host "`n=== Migrations ===" -ForegroundColor Cyan
        Push-Location (Join-Path $root 'services\api')
        try {
            $previous = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            & .\.venv\Scripts\alembic.exe upgrade head 2>&1 | ForEach-Object { "$_" }
            $exit = $LASTEXITCODE
            $ErrorActionPreference = $previous
            if ($exit -ne 0) { throw "alembic upgrade failed (exit $exit)" }
        } finally { Pop-Location }

        Write-Host "`nDatabase ready, with pgvector." -ForegroundColor Green
    }

    'down' { Invoke-Docker -Arguments 'compose down' -WorkingDirectory $root | Out-Null }

    'status' {
        Invoke-Docker -Arguments 'compose ps' -WorkingDirectory $root | Out-Null
        Write-Host "health: $(Get-DockerContainerHealth)"
    }

    'reset' {
        Write-Host 'This destroys the database volume.' -ForegroundColor Yellow
        Invoke-Docker -Arguments 'compose down -v' -WorkingDirectory $root | Out-Null
        Write-Host 'Volume removed. Run -Action up to recreate.' -ForegroundColor Green
    }
}
