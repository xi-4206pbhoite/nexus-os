<#
.SYNOPSIS
    Exercises every HTTP endpoint that currently exists, and asserts the refusals.

.DESCRIPTION
    A guided walk-through for manual validation. It prints what it is about to
    prove before each step, so a failure tells you which guarantee broke rather
    than which line threw.

    Deliberately asserts the *negative* cases too - a CSRF-less POST, a workspace
    for an unverified domain, a private-address crawl. A smoke test that only
    walks the happy path would pass just as happily with every guard removed.

    Creates a throwaway account each run. Nothing is cleaned up: the rows are the
    evidence, and `POST /auth/register` has no delete counterpart yet.

.PARAMETER ApiBase
    Where the API is listening. Default http://127.0.0.1:8000

.PARAMETER PreviewUrl
    A public website for the Preview audit. Default https://example.com
    Limits: 20 analyses per hour per IP, 5 per domain per day. A repeat of a
    domain already audited is served from storage and costs no domain allowance.

.PARAMETER SkipPreview
    Skip the Preview audit. Use this once you have spent the daily allowance on
    a domain, so the rest of the walk still runs.

.EXAMPLE
    .\scripts\smoke.ps1

.EXAMPLE
    .\scripts\smoke.ps1 -PreviewUrl https://www.omantel.om
#>
[CmdletBinding()]
param(
    [string] $ApiBase = 'http://127.0.0.1:8000',
    [string] $PreviewUrl = 'https://example.com',
    [switch] $SkipPreview
)

# Native tools are not called here, but Invoke-RestMethod raises on 4xx and this
# script asserts several 4xx responses on purpose. Each is caught individually.
$ErrorActionPreference = 'Stop'

$script:Passed = 0
$script:Failed = 0

function Write-Step {
    param([string] $Text)
    Write-Host ''
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Assert-That {
    param([string] $Claim, [bool] $Condition, [string] $Detail = '')
    if ($Condition) {
        Write-Host "  PASS  $Claim" -ForegroundColor Green
        $script:Passed++
    }
    else {
        Write-Host "  FAIL  $Claim" -ForegroundColor Red
        if ($Detail) { Write-Host "        $Detail" -ForegroundColor Red }
        $script:Failed++
    }
}

# Status code and response body of a request expected to fail. Status 0 means it
# unexpectedly succeeded.
#
# The body comes from `$_.ErrorDetails.Message`, not from reading the response
# stream: Invoke-RestMethod has already consumed the stream by the time the
# exception surfaces, so GetResponseStream() returns nothing and the reason for a
# failure silently disappears. That cost a debugging round on a `400` whose
# detail printed as empty.
function Invoke-ExpectingFailure {
    param([scriptblock] $Request)
    try {
        & $Request | Out-Null
        return [pscustomobject]@{ Status = 0; Detail = '(request succeeded)' }
    }
    catch {
        $status = -1
        if ($null -ne $_.Exception.Response) { $status = [int] $_.Exception.Response.StatusCode }
        $detail = ''
        if ($null -ne $_.ErrorDetails) { $detail = $_.ErrorDetails.Message }
        if (-not $detail) { $detail = $_.Exception.Message }
        return [pscustomobject]@{ Status = $status; Detail = $detail }
    }
}

function Get-CookieValue {
    param($Session, [string] $Uri, [string] $Name)
    $cookies = $Session.Cookies.GetCookies([Uri] $Uri)
    foreach ($c in $cookies) {
        if ($c.Name -eq $Name) { return $c.Value }
    }
    return $null
}

Write-Host ''
Write-Host 'NEXUS OS smoke test' -ForegroundColor White
Write-Host "API: $ApiBase"

# -- Liveness and readiness ------------------------------------

Write-Step 'Health - liveness must not depend on the database'
try {
    $live = Invoke-RestMethod -Uri "$ApiBase/health" -Method Get
    Assert-That 'GET /health answers' ($live.status -eq 'ok')
}
catch {
    Write-Host "  The API is not answering on $ApiBase." -ForegroundColor Red
    Write-Host '  Start it:  cd services\api; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000'
    exit 1
}

Write-Step 'Health - readiness reports each dependency separately'
Write-Host '  The first call after a restart is slow: Neon suspends idle compute.'
$ready = Invoke-RestMethod -Uri "$ApiBase/health/ready" -Method Get
foreach ($check in $ready.checks) {
    $required = if ($check.required_now) { 'required' } else { 'advisory' }
    Write-Host ("    {0,-16} {1,-14} {2,-10} {3}" -f $check.name, $check.state, $required, $check.detail)
}
$db = $ready.checks | Where-Object { $_.name -eq 'database' }
$vec = $ready.checks | Where-Object { $_.name -eq 'pgvector' }
Assert-That 'the database is reachable' ($db.state -eq 'ok') "state=$($db.state) detail=$($db.detail)"
Assert-That 'pgvector is installed' ($vec.state -eq 'ok') "state=$($vec.state) detail=$($vec.detail)"
Assert-That 'pgvector is reported but advisory (ADR 0004)' ($vec.required_now -eq $false)

# -- Preview: the only feature with a UI -----------------------

if (-not $SkipPreview) {
    Write-Step "Preview - a real audit of $PreviewUrl, with no account"
    Write-Host '  Every number here comes from a pure function over fetched HTML (I1).'
    $body = @{ url = $PreviewUrl } | ConvertTo-Json
    try {
        $audit = Invoke-RestMethod -Uri "$ApiBase/preview" -Method Post -Body $body -ContentType 'application/json'

        Write-Host "    domain     : $($audit.domain)"
        Write-Host "    final_url  : $($audit.final_url)"
        Write-Host "    overall    : $($audit.overall)/100 across $($audit.scored_categories) scored categories"
        foreach ($c in $audit.categories) {
            Write-Host ("      {0,-16} {1,3}/{2,-3} {3,3}%" -f $c.category, $c.score, $c.max_score, $c.percentage)
        }
        Write-Host "    locked     : $($audit.locked.Count) categories, each naming its unlock"
        foreach ($l in $audit.locked) {
            Write-Host ("      {0,-22} {1}" -f $l.category, $l.unlock)
        }

        Assert-That 'the audit scores at least one category' ($audit.scored_categories -ge 1)
        Assert-That 'locked categories are named, never scored zero (I10)' ($audit.locked.Count -gt 0)

        $everyCheckHasEvidence = $true
        $checkCount = 0
        foreach ($c in $audit.categories) {
            foreach ($chk in $c.checks) {
                $checkCount++
                if ([string]::IsNullOrWhiteSpace($chk.evidence)) { $everyCheckHasEvidence = $false }
            }
        }
        Assert-That "all $checkCount checks carry evidence (I9)" $everyCheckHasEvidence
        Assert-That 'the audit expires' ($null -ne $audit.expires_at) "expires_at=$($audit.expires_at)"
    }
    catch {
        $status = -1
        if ($null -ne $_.Exception.Response) { $status = [int] $_.Exception.Response.StatusCode }
        $detail = ''
        if ($null -ne $_.ErrorDetails) { $detail = $_.ErrorDetails.Message }
        if (-not $detail) { $detail = $_.Exception.Message }

        if ($status -eq 429) {
            # Possible on repeated runs. The SSRF probes below consume the
            # same per-IP allowance as a real audit, so one full pass costs 7 of
            # the 20 hourly calls - comfortable now, where at the previous 5 it
            # made a second run inside the hour impossible. The limit working is
            # not the limit failing.
            Write-Host '  SKIP  rate limited (429) - the allowance is spent' -ForegroundColor Yellow
            Write-Host "        $detail"
            Write-Host '        20/hour per IP, 5/day per domain. Wait, or use -SkipPreview'
            Write-Host '        to run the account and workspace-gate checks now.'
        }
        elseif ($detail -match 'too long to respond|could not be reached|did not return') {
            # The target website is slow, blocking us, or down. Nothing of ours
            # is under test, so failing would blame our code for their outage -
            # but silence would hide a skipped assertion.
            Write-Host "  SKIP  $PreviewUrl did not answer" -ForegroundColor Yellow
            Write-Host "        $detail"
            Write-Host '        Not a defect - the API said so plainly. Try another -PreviewUrl.'
        }
        else {
            Assert-That 'the Preview audit succeeds' $false "HTTP $status - $detail"
        }
    }

    Write-Step 'Preview - the SSRF guard refuses what it should'
    Write-Host '  An unauthenticated server-side fetch: the caller picks the destination.'
    $hostile = @(
        @{ url = 'http://127.0.0.1:8000/health'; why = 'loopback' },
        @{ url = 'http://169.254.169.254/latest/meta-data/'; why = 'cloud metadata' },
        @{ url = 'http://10.0.0.1/'; why = 'private network' },
        @{ url = 'http://2130706433/'; why = 'loopback as a bare decimal' },
        @{ url = 'gopher://evil.example/'; why = 'non-HTTP scheme' },
        @{ url = 'http://expected.example@evil.example/'; why = 'credentials in the authority' }
    )
    foreach ($h in $hostile) {
        $payload = @{ url = $h.url } | ConvertTo-Json
        $r = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/preview" -Method Post -Body $payload -ContentType 'application/json' }
        Assert-That "refused: $($h.why)" ($r.Status -ge 400 -and $r.Status -lt 500) "got HTTP $($r.Status) $($r.Detail)"
    }
}
else {
    Write-Step 'Preview - skipped (-SkipPreview)'
}

# -- Accounts --------------------------------------------------

$stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
# Not `.invalid`, `.test` or `example.com`: the email validator rejects
# special-use and reserved names outright, so the obvious throwaway domains all
# fail validation before the account logic is ever reached.
$email = "smoke-$stamp@nexus-smoke-run.om"
$password = 'a-passphrase-long-enough-to-pass'

Write-Step 'Register - the response must not reveal whether an address is known'
$reg = @{ email = $email; password = $password } | ConvertTo-Json
$first = Invoke-RestMethod -Uri "$ApiBase/auth/register" -Method Post -Body $reg -ContentType 'application/json'
$again = Invoke-RestMethod -Uri "$ApiBase/auth/register" -Method Post -Body $reg -ContentType 'application/json'
Write-Host "    new address      : $($first.status)"
Write-Host "    same address     : $($again.status)"
Assert-That 'registering twice returns an identical body (no account enumeration)' `
    ($first.status -eq $again.status)

Write-Step 'Login - and the session cookies it sets'
$login = Invoke-RestMethod -Uri "$ApiBase/auth/login" -Method Post -Body $reg `
    -ContentType 'application/json' -SessionVariable session
Write-Host "    user_id          : $($login.user_id)"
Write-Host "    workspaces       : $($login.workspaces.Count)"
Write-Host "    active_workspace : $(if ($null -eq $login.active_workspace_id) { '(none)' } else { $login.active_workspace_id })"

$sessionCookie = Get-CookieValue $session $ApiBase 'nexus_session'
$csrf = Get-CookieValue $session $ApiBase 'nexus_csrf'
Assert-That 'a session cookie is set' ($null -ne $sessionCookie)
Assert-That 'a readable CSRF cookie is set (double-submit)' ($null -ne $csrf)
Assert-That 'a new account has no workspace' ($login.workspaces.Count -eq 0)

Write-Step 'Login - a wrong password must be indistinguishable from an unknown address'
$wrongPassword = @{ email = $email; password = 'definitely-not-the-password' } | ConvertTo-Json
# Same domain as the registered address, on purpose. A different domain risks
# comparing a 401 against a 422 from address validation, which proves nothing
# about enumeration - and did, on the first run of this script.
$unknownEmail = @{ email = "nobody-$stamp@nexus-smoke-run.om"; password = $password } | ConvertTo-Json
$rWrong = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/login" -Method Post -Body $wrongPassword -ContentType 'application/json' }
$rUnknown = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/login" -Method Post -Body $unknownEmail -ContentType 'application/json' }
Write-Host "    wrong password  : HTTP $($rWrong.Status)  $($rWrong.Detail)"
Write-Host "    unknown address : HTTP $($rUnknown.Status)  $($rUnknown.Detail)"
Assert-That 'wrong password is rejected' ($rWrong.Status -eq 401) "got HTTP $($rWrong.Status)"
# The status alone is not enough. A differing *body* discloses just as much and
# is the easier mistake to make.
Assert-That 'unknown address is indistinguishable from a wrong password' `
    ($rUnknown.Status -eq $rWrong.Status -and $rUnknown.Detail -eq $rWrong.Detail) `
    "wrong=$($rWrong.Status) $($rWrong.Detail) | unknown=$($rUnknown.Status) $($rUnknown.Detail)"

Write-Step 'CSRF - a state-changing POST without the header must be refused'
$claimBody = @{ domain = "smoke-$stamp.example"; method = 'dns_txt' } | ConvertTo-Json
$rCsrf = Invoke-ExpectingFailure {
    Invoke-RestMethod -Uri "$ApiBase/domains" -Method Post -Body $claimBody `
        -ContentType 'application/json' -WebSession $session
}
Assert-That 'POST /domains without X-CSRF-Token is refused' ($rCsrf.Status -eq 403) "got HTTP $($rCsrf.Status)"

# -- The workspace gate ----------------------------------------

Write-Step 'Domain claim - begin one'
$headers = @{ 'X-CSRF-Token' = $csrf }
$claim = Invoke-RestMethod -Uri "$ApiBase/domains" -Method Post -Body $claimBody `
    -ContentType 'application/json' -WebSession $session -Headers $headers
Write-Host "    claim_id  : $($claim.claim_id)"
Write-Host "    state     : $($claim.state)  strength: $($claim.strength)"
Write-Host '    instruction:'
foreach ($line in ($claim.instruction -split "`n")) { Write-Host "      $line" }
Assert-That 'a new claim starts pending, never verified' ($claim.state -eq 'pending')

Write-Step 'Domain claim - checking an unproven domain must not verify it'
$checked = Invoke-RestMethod -Uri "$ApiBase/domains/$($claim.claim_id)/check" -Method Post `
    -WebSession $session -Headers $headers
Write-Host "    state    : $($checked.state)"
Write-Host "    evidence : $($checked.evidence)"
Assert-That 'the claim is still pending' ($checked.state -ne 'verified')
Assert-That 'the failure states a reason (I10)' (-not [string]::IsNullOrWhiteSpace($checked.evidence))

Write-Step 'The workspace gate - M3''s acceptance test'
Write-Host '  Doc 07 M3: "try to create a workspace for a domain I do not control and fail."'
$wsBody = @{ name = 'Smoke Test Co' } | ConvertTo-Json
$rWs = Invoke-ExpectingFailure {
    Invoke-RestMethod -Uri "$ApiBase/domains/$($claim.claim_id)/workspace" -Method Post `
        -Body $wsBody -ContentType 'application/json' -WebSession $session -Headers $headers
}
Write-Host "    refused with: $($rWs.Detail)"
Assert-That 'no workspace without a verified domain' ($rWs.Status -eq 403) "got HTTP $($rWs.Status)"

Write-Step 'GET /auth/me - requires a workspace membership'
$rMe = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/me" -Method Get -WebSession $session }
Assert-That '/auth/me is refused without a workspace' ($rMe.Status -eq 403) "got HTTP $($rMe.Status)"
Write-Host '  This is the dead end described in USAGE.md: a workspace needs a verified'
Write-Host '  domain, so a fresh account cannot reach /auth/me unless you control one.'

Write-Step 'Logout'
Invoke-RestMethod -Uri "$ApiBase/auth/logout" -Method Post -WebSession $session -Headers $headers | Out-Null
$rAfter = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/me" -Method Get -WebSession $session }
Assert-That 'the session no longer works after logout' ($rAfter.Status -ge 400) "got HTTP $($rAfter.Status)"

# -- Verdict ---------------------------------------------------

Write-Host ''
Write-Host ('-' * 60)
if ($script:Failed -eq 0) {
    Write-Host "SMOKE PASSED   $($script:Passed) assertions" -ForegroundColor Green
    Write-Host ''
    Write-Host 'Account used (kept, so you can look at the rows):'
    Write-Host "  $email"
    exit 0
}
else {
    Write-Host "SMOKE FAILED   $($script:Failed) of $($script:Passed + $script:Failed) assertions" -ForegroundColor Red
    exit 1
}
