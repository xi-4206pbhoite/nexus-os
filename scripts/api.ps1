<#
.SYNOPSIS
    Runs the API, optionally with auto-reload.

.DESCRIPTION
    Exists so nobody has to remember the uvicorn invocation, and because reload
    needs care on this project.

    Two things about -Reload worth knowing before you rely on it:

    - It watches `services\api\app` only. Pointing it at the repository root
      makes it watch `.venv`, `node_modules` and `.storage`, which is tens of
      thousands of files - it either burns CPU or silently gives up.
    - The reloader replaces the worker process, which tears down the APScheduler
      thread and reopens every database connection. Against Neon that means the
      first request after a reload pays the cold-connect cost again (~6s).

    A reload that appears to hang - the "Reloading..." line with no
    "Application startup complete" after it - means the new worker never came up.
    Stop with Ctrl+C and start again; the usual cause is a syntax error in the
    file you just saved, which uvicorn reports on stderr before dying.

.PARAMETER Reload
    Restart the worker when a file under `app\` changes. For development only:
    it doubles the process count and drops the connection pool on every save.

.PARAMETER Port
    Default 8000, which is what apps\web expects.

.EXAMPLE
    .\scripts\api.ps1

.EXAMPLE
    .\scripts\api.ps1 -Reload
#>
[CmdletBinding()]
param(
    [switch] $Reload,
    [int] $Port = 8000,
    [string] $BindAddress = '127.0.0.1'
)

# uvicorn logs to stderr, and under `Stop` that would abort a healthy start.
$ErrorActionPreference = 'Continue'

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot 'services\api'
$python = Join-Path $apiDir '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host "No virtualenv at $python" -ForegroundColor Red
    Write-Host 'Run .\scripts\setup.ps1 first.'
    exit 1
}

$envFile = Join-Path $repoRoot '.env'
if (-not (Test-Path $envFile)) {
    Write-Host "No .env at $envFile - the API will refuse to start." -ForegroundColor Red
    Write-Host 'Run .\scripts\setup.ps1 first.'
    exit 1
}

$arguments = @(
    '-m', 'uvicorn', 'app.main:app',
    '--host', $BindAddress,
    '--port', $Port
)

if ($Reload) {
    # `app` is relative to the working directory set below.
    $arguments += @('--reload', '--reload-dir', 'app')
    Write-Host 'Auto-reload ON - watching services\api\app' -ForegroundColor Yellow
    Write-Host 'Each reload drops the connection pool; the next request re-connects to Neon.'
}

Write-Host "API on http://${BindAddress}:${Port}   (Ctrl+C to stop)" -ForegroundColor Cyan
Write-Host "docs at http://${BindAddress}:${Port}/docs"
Write-Host ''

Push-Location $apiDir
try {
    & $python @arguments
}
finally {
    Pop-Location
}
