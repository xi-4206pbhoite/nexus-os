# One-time local setup. Per ADR 0001 there is no Docker; this replaces
# `docker compose up` as the way the stack is prepared.
# Usage:  .\scripts\setup.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Write-Host '=== Python 3.12 ===' -ForegroundColor Cyan
$py312 = $null
foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                 "$env:ProgramFiles\Python312\python.exe")) {
    if (Test-Path $c) { $py312 = $c; break }
}
if (-not $py312) {
    try { $v = & py -3.12 --version 2>$null; if ($v) { $py312 = 'py -3.12' } } catch {}
}
if (-not $py312) {
    Write-Host 'Python 3.12 not found. Install it with:' -ForegroundColor Red
    Write-Host '  winget install --id Python.Python.3.12 --scope user' -ForegroundColor Yellow
    exit 1
}
Write-Host "found: $py312"

Write-Host "`n=== API virtualenv ===" -ForegroundColor Cyan
Push-Location (Join-Path $root 'services\api')
try {
    if (-not (Test-Path '.venv')) {
        if ($py312 -eq 'py -3.12') { & py -3.12 -m venv .venv } else { & $py312 -m venv .venv }
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    & .\.venv\Scripts\python.exe -m pip install -e ".[dev]" --quiet
    Write-Host 'API dependencies installed.'
} finally { Pop-Location }

Write-Host "`n=== Web dependencies ===" -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps\web')
try {
    if (-not (Test-Path 'node_modules')) { npm ci } else { Write-Host 'node_modules present.' }
} finally { Pop-Location }

Write-Host "`n=== Environment file ===" -ForegroundColor Cyan
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Write-Host 'Created .env from .env.example.' -ForegroundColor Yellow
    Write-Host 'It needs NEXUS_DATABASE_URL (a pgvector-enabled Postgres) before migrations run.'
} else {
    Write-Host '.env already exists -- left untouched.'
}

Write-Host "`n=== Database ===" -ForegroundColor Cyan
if (Test-Path 'D:\PostgreSQL\pgsql\bin\pg_ctl.exe') {
    Write-Host 'Local PostgreSQL present.'
    Write-Host '  start:  .\scripts\pg-local.ps1 -Action start'
    Write-Host '  init :  .\scripts\db-init.ps1 -SuperPassword (Get-Content D:\PostgreSQL\superuser.pw)'
} else {
    Write-Host 'No local PostgreSQL. Per ADR 0001 (no Docker), install the self-contained cluster:' -ForegroundColor Yellow
    Write-Host '  1. Download the EnterpriseDB binaries zip for PostgreSQL 17 (x64)'
    Write-Host '  2. .\scripts\pg-local.ps1 -Action install -ZipPath <zip>'
    Write-Host '  3. .\scripts\pg-local.ps1 -Action start'
    Write-Host '  4. .\scripts\db-init.ps1 -SuperPassword (Get-Content D:\PostgreSQL\superuser.pw)'
    Write-Host 'Note: pgvector is not in the stock build. Not needed until M5 - see ADR 0004.'
}

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host 'Start the API:  cd services\api; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000'
Write-Host 'Start the web:  npm run dev --prefix apps\web'
Write-Host 'Run the gate :  .\scripts\ci.ps1'
