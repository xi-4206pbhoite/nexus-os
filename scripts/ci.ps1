# Runs exactly what .github/workflows/ci.yml runs.
#
# The suite needs a real PostgreSQL. Ninety-two tests assert database
# behaviour - row-level security above all - and without one they used to
# skip while the run still reported green. They no longer can:
# tests/test_ci_contract.py fails when no database is configured, and
# conftest.py fails the session if a requires_db test skips.
#
# The URL comes from $env:NEXUS_DATABASE_URL, or from .env when that is
# unset. For a database built the way CI builds it - bootstrap.sql, then
# migrations in both directions on a clean local cluster - run
# .\scripts\db-ci.ps1 first.
#
# Usage:  .\scripts\ci.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Invoke-Step {
    param([string]$Name, [string]$Dir, [scriptblock]$Body)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root $Dir)

    # Windows PowerShell 5.1 wraps a native command's stderr in an ErrorRecord,
    # which $ErrorActionPreference='Stop' turns into a terminating error. Tools
    # here write ordinary output to stderr - npm update notices, ruff's summary,
    # alembic's INFO - so the strict preference reports a passing step as a
    # failure. An `npm notice` failed the whole gate while tsc exited 0.
    # Relax around the call and branch on the real exit code.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Body 2>&1 | ForEach-Object { "$_" }
        $exit = $LASTEXITCODE
        if ($exit -ne 0) { throw "exit $exit" }
        Write-Host "PASS  $Name" -ForegroundColor Green
    } catch {
        Write-Host "FAIL  $Name -- $_" -ForegroundColor Red
        $script:failed += $Name
    } finally {
        $ErrorActionPreference = $previous
        Pop-Location
    }
}

# Every script must parse. This has caught the same defect twice, and it is one
# nothing else in the gate can see: a .ps1 with no UTF-8 BOM is read as CP1252 by
# Windows PowerShell 5.1, so a non-ASCII character inside a *string literal*
# becomes three characters - one of which is a smart quote that terminates the
# string early and turns the rest of the line into code.
#
# Deliberately a parse check rather than a ban on non-ASCII: db-init.ps1 has 277
# box-drawing characters in comments and is perfectly fine, because a stray quote
# in a comment breaks nothing. The parse is what actually matters, and it catches
# ordinary syntax errors too - a script that only runs on the user's machine is
# otherwise tested by them, by hand, at the worst moment.
Write-Host "`n=== scripts: parse ===" -ForegroundColor Cyan
$parseFailures = @()
foreach ($script in Get-ChildItem (Join-Path $root 'scripts') -Filter *.ps1 -Recurse) {
    $errors = $null
    # Read the way PowerShell itself will, so mojibake is reproduced, not avoided.
    $text = Get-Content -Raw -LiteralPath $script.FullName
    [void][System.Management.Automation.PSParser]::Tokenize($text, [ref]$errors)
    if ($errors.Count -gt 0) {
        $first = $errors[0]
        $relative = $script.FullName.Substring($root.Length + 1)
        Write-Host "  $relative line $($first.Token.StartLine): $($first.Message)" -ForegroundColor Red
        $parseFailures += $relative
    }
}
if ($parseFailures.Count -gt 0) {
    Write-Host "FAIL  scripts: parse -- $($parseFailures -join ', ')" -ForegroundColor Red
    $failed += 'scripts: parse'
} else {
    Write-Host 'PASS  scripts: parse' -ForegroundColor Green
}

$venv = Join-Path $root 'services\api\.venv\Scripts'
$py   = Join-Path $venv 'python.exe'
if (-not (Test-Path $py)) {
    Write-Host "No API virtualenv at services\api\.venv -- run .\scripts\setup.ps1 first." -ForegroundColor Yellow
} else {
    Invoke-Step 'api: ruff check'   'services\api' { & (Join-Path $venv 'ruff.exe') check . }
    Invoke-Step 'api: ruff format'  'services\api' { & (Join-Path $venv 'ruff.exe') format --check . }
    # 'app tests' rather than 'app'. The suite is what proves the
    # invariants, so untyped test code is untyped proof.
    Invoke-Step 'api: mypy strict'  'services\api' { & (Join-Path $venv 'mypy.exe') app tests }
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
