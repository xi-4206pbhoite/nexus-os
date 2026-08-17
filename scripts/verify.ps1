# One-command validation of the current milestone.
#
# Runs the same gate CI runs, then probes whatever is running. Exists so
# validating a milestone never requires composing shell commands by hand —
# Windows PowerShell 5.1 has no `&&`, and `curl` is an alias for
# Invoke-WebRequest, so copied bash one-liners fail in confusing ways.
#
# Usage:  .\scripts\verify.ps1
#         .\scripts\verify.ps1 -SkipGate      # probes only, much faster

param([switch]$SkipGate)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$results = [ordered]@{}

function Show([string]$Name, [bool]$Ok, [string]$Detail) {
    $results[$Name] = $Ok
    $mark = if ($Ok) { 'PASS' } else { 'FAIL' }
    $colour = if ($Ok) { 'Green' } else { 'Red' }
    Write-Host ('{0,-6}{1,-26}{2}' -f $mark, $Name, $Detail) -ForegroundColor $colour
}

function Probe([string]$Url) {
    try {
        # Invoke-WebRequest, not curl: in PS 5.1 `curl` is an alias for this
        # anyway, and calling it directly makes the status code accessible.
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        # Decode explicitly: PS 5.1 does not honour the charset on .Content, so
        # UTF-8 in a JSON detail string arrives mojibaked.
        $body = [System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
        return @{ ok = $true; code = $r.StatusCode; body = $body }
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        $body = ''
        if ($_.Exception.Response) {
            try {
                $sr = New-Object System.IO.StreamReader(
                    $_.Exception.Response.GetResponseStream(), [System.Text.Encoding]::UTF8)
                $body = $sr.ReadToEnd()
            } catch {}
        }
        return @{ ok = $false; code = $code; body = $body }
    }
}

Write-Host "`n=== Infrastructure ===" -ForegroundColor Cyan

# Two backends can serve 5432 (ADR 0006 Docker, ADR 0001 native). Report which
# one is actually answering — a passing check against the wrong database is
# worse than a failing one.
$backend = 'none'
. (Join-Path $PSScriptRoot 'lib\docker.ps1')
if ((Get-DockerMode) -ne 'none') {
    if ((Get-DockerContainerHealth) -eq 'healthy') {
        $backend = "docker/$(Get-DockerMode) (pgvector image)"
    }
}

$pgReady = 'D:\PostgreSQL\pgsql\bin\pg_isready.exe'
$reachable = $false
if (Test-Path $pgReady) {
    & $pgReady -h 127.0.0.1 -p 5432 | Out-Null
    $reachable = ($LASTEXITCODE -eq 0)
    if ($reachable -and $backend -eq 'none') { $backend = 'native cluster' }
}

if ($backend -eq 'none' -and -not $reachable) {
    Show 'postgres' $false 'nothing on 127.0.0.1:5432 - see scripts\db-docker.ps1'
} else {
    Show 'postgres' $true "127.0.0.1:5432 via $backend"
}

Write-Host "`n=== Services (start them first if these fail) ===" -ForegroundColor Cyan

$live = Probe 'http://127.0.0.1:8000/health'
Show 'api /health' ($live.ok -and $live.code -eq 200) "HTTP $($live.code)"

$ready = Probe 'http://127.0.0.1:8000/health/ready'
if ($ready.body) {
    try {
        $json = $ready.body | ConvertFrom-Json
        Show 'api /health/ready' ($json.status -eq 'ok') "HTTP $($ready.code) - status=$($json.status)"
        foreach ($c in $json.checks) {
            $req = if ($c.required_now) { 'required' } else { 'advisory' }
            $ok = ($c.state -eq 'ok') -or (-not $c.required_now)
            Show "  $($c.name)" $ok "$($c.state) [$req] $($c.detail)"
        }
    } catch {
        Show 'api /health/ready' $false "unparseable: $($ready.code)"
    }
} else {
    Show 'api /health/ready' $false 'no response - is the API running?'
}

$web = Probe 'http://localhost:3000/api/health'
if ($web.body) {
    try {
        $json = $web.body | ConvertFrom-Json
        Show 'web /api/health' ($json.status -eq 'ok') "api=$($json.api)"
    } catch { Show 'web /api/health' $false 'unparseable' }
} else {
    Show 'web /api/health' $false 'no response - is the web app running?'
}

if (-not $SkipGate) {
    Write-Host "`n=== Gate ===" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'ci.ps1') | Select-String -Pattern '^(PASS|FAIL|CI )' |
        ForEach-Object { Write-Host $_ }
    Show 'gate' ($LASTEXITCODE -eq 0) 'scripts\ci.ps1'
}

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$failed = $results.GetEnumerator() | Where-Object { -not $_.Value }
if ($failed) {
    Write-Host "FAILED: $(($failed | ForEach-Object { $_.Key }) -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host 'ALL GREEN' -ForegroundColor Green
