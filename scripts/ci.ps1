# Runs exactly what .github/workflows/ci.yml runs.
# Per ADR 0002 there is no remote yet, so this is the real gate for now.
# Usage:  .\scripts\ci.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Invoke-Step {
    param([string]$Name, [string]$Dir, [scriptblock]$Body)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root $Dir)
    try {
        & $Body
        if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        Write-Host "PASS  $Name" -ForegroundColor Green
    } catch {
        Write-Host "FAIL  $Name -- $_" -ForegroundColor Red
        $script:failed += $Name
    } finally {
        Pop-Location
    }
}

$venv = Join-Path $root 'services\api\.venv\Scripts'
$py   = Join-Path $venv 'python.exe'
if (-not (Test-Path $py)) {
    Write-Host "No API virtualenv at services\api\.venv -- run .\scripts\setup.ps1 first." -ForegroundColor Yellow
} else {
    Invoke-Step 'api: ruff check'   'services\api' { & (Join-Path $venv 'ruff.exe') check . }
    Invoke-Step 'api: ruff format'  'services\api' { & (Join-Path $venv 'ruff.exe') format --check . }
    Invoke-Step 'api: mypy strict'  'services\api' { & (Join-Path $venv 'mypy.exe') app }
    Invoke-Step 'api: pytest'       'services\api' { & (Join-Path $venv 'pytest.exe') -q }
}

Invoke-Step 'web: tsc'    'apps\web' { npx tsc --noEmit }
Invoke-Step 'web: lint'   'apps\web' { npx next lint }
Invoke-Step 'web: build'  'apps\web' { npx next build }

Write-Host ''
if ($failed.Count -gt 0) {
    Write-Host "CI FAILED: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host 'CI GREEN' -ForegroundColor Green
