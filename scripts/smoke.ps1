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

.PARAMETER MailRoot
    Where the file mailer writes. Default .mail - the same default as
    NEXUS_MAIL_ROOT. The walk reads the verification and reset emails from here,
    which is how it can follow a link without a provider or a mailbox.

.EXAMPLE
    .\scripts\smoke.ps1
#>
[CmdletBinding()]
param(
    [string] $ApiBase = 'http://127.0.0.1:8000',
    [string] $MailRoot = '.mail'
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

# The newest message the file mailer wrote, as text.
#
# This is what makes the verification and reset paths walkable with no provider
# and no mailbox: `FileMailer` writes RFC-822 to disk, so the link a real user
# would click is sitting in a file. `-Raw` matters - without it the body comes
# back as an array of lines and the regex below never matches across the wrap.
function Get-NewestMail {
    param([string] $Root)
    if (-not (Test-Path $Root)) { return $null }
    $newest = Get-ChildItem -Path $Root -Filter '*.eml' | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($null -eq $newest) { return $null }
    return Get-Content -Path $newest.FullName -Raw
}

# Pull a single-use token out of a link in an email body.
function Get-TokenFrom {
    param([string] $Body, [string] $Path)
    if ([string]::IsNullOrWhiteSpace($Body)) { return $null }
    # The quoted-printable encoder may wrap a long URL with `=` + newline.
    $joined = $Body -replace "=\r?\n", ''
    $pattern = [regex]::Escape($Path) + '\?token=([A-Za-z0-9_\-]+)'
    $m = [regex]::Match($joined, $pattern)
    if (-not $m.Success) { return $null }
    return $m.Groups[1].Value
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

# -- The preview is gone, and that is asserted ------------------

# Phase 2 retired the unauthenticated audit (`doc/11` Q1). This block used to
# run a real crawl with no account and then fire six SSRF probes at it. Both are
# deleted rather than skipped, because there is no longer an endpoint to skip.
#
# What replaces them is one assertion, and it is the one that matters: nothing
# answers there any more. The SSRF guard itself is not weaker for it - it moved
# to `app/research/` and its 89 cases still run in `tests/test_ssrf_guard.py`,
# which is a better venue than a smoke test that needed a live third-party
# website to say anything at all.

Write-Step 'The unauthenticated audit is gone'
$rPreview = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/preview" -Method Post -Body '{"url":"https://example.com"}' -ContentType 'application/json' }
Assert-That 'POST /preview returns 404' ($rPreview.Status -eq 404) "got HTTP $($rPreview.Status)"
Write-Host '  A stranger could point this at any company and be handed an analysis of it.'
Write-Host '  The engine survives behind authentication; the entry point does not.'

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

# -- Verification and password reset (P3) ----------------------

Write-Step 'Registering sent a verification email'
Write-Host '  Read from disk, not asserted from the API response: the claim is that'
Write-Host '  something was actually delivered, and the .eml file is the evidence.'
$mail = Get-NewestMail -Root $MailRoot
Assert-That "a message was written to $MailRoot" ($null -ne $mail) 'no .eml found - is NEXUS_MAILER_BACKEND=file?'

$verifyToken = Get-TokenFrom -Body $mail -Path '/verify-email'
Assert-That 'the email carries a /verify-email link with a token' ($null -ne $verifyToken)

if ($null -ne $verifyToken) {
    $vBody = @{ token = $verifyToken } | ConvertTo-Json
    $verified = Invoke-RestMethod -Uri "$ApiBase/auth/verify-email" -Method Post -Body $vBody -ContentType 'application/json'
    Assert-That 'the token verifies the address' ($verified.status -eq 'verified')

    $rReuse = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/verify-email" -Method Post -Body $vBody -ContentType 'application/json' }
    Assert-That 'the same token cannot be used twice' ($rReuse.Status -eq 400) "got HTTP $($rReuse.Status)"
}

Write-Step 'Password reset reveals nothing about who has an account'
$known = @{ email = $email } | ConvertTo-Json
$unknown = @{ email = "nobody-$stamp@nexus-smoke-run.om" } | ConvertTo-Json
$realReply = Invoke-RestMethod -Uri "$ApiBase/auth/password-reset/request" -Method Post -Body $known -ContentType 'application/json'
$fakeReply = Invoke-RestMethod -Uri "$ApiBase/auth/password-reset/request" -Method Post -Body $unknown -ContentType 'application/json'
Write-Host "    known address    : $($realReply.status)"
Write-Host "    unknown address  : $($fakeReply.status)"
Assert-That 'both addresses get an identical reply' ($realReply.status -eq $fakeReply.status)
Write-Host '  A one-word difference here would be a complete account-enumeration oracle,'
Write-Host '  on an endpoint that needs no account to reach.'

Write-Step 'The reset link works once, and ends every session'
# Held before the reset, because the reset is about to revoke it and the
# assertion below is the whole point of doing so.
$preResetSession = $session
$resetMail = Get-NewestMail -Root $MailRoot
$resetToken = Get-TokenFrom -Body $resetMail -Path '/reset-password'
Assert-That 'the reset email carries a token' ($null -ne $resetToken)

if ($null -ne $resetToken) {
    $newPassword = 'a-second-passphrase-long-enough'
    $confirm = @{ token = $resetToken; password = $newPassword } | ConvertTo-Json
    $done = Invoke-RestMethod -Uri "$ApiBase/auth/password-reset/confirm" -Method Post -Body $confirm -ContentType 'application/json'
    Assert-That 'the password is updated' ($done.status -eq 'password_updated')

    $rOld = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/login" -Method Post -Body $reg -ContentType 'application/json' }
    Assert-That 'the old password stops working' ($rOld.Status -eq 401) "got HTTP $($rOld.Status)"

    # `-SessionVariable` on purpose: this replaces `$session`, which the reset
    # has just revoked. The Logout step below needs a live one, and its CSRF
    # cookie is new too - reusing the old `$headers` would fail the
    # double-submit check rather than the thing that step is testing.
    $newLogin = @{ email = $email; password = $newPassword } | ConvertTo-Json
    $after = Invoke-RestMethod -Uri "$ApiBase/auth/login" -Method Post -Body $newLogin `
        -ContentType 'application/json' -SessionVariable session
    Assert-That 'the new password works' ($null -ne $after.user_id)
    $headers = @{ 'X-CSRF-Token' = (Get-CookieValue $session $ApiBase 'nexus_csrf') }

    $rSpent = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/password-reset/confirm" -Method Post -Body $confirm -ContentType 'application/json' }
    Assert-That 'the reset token cannot be reused' ($rSpent.Status -eq 400) "got HTTP $($rSpent.Status)"

    # The session opened before the reset must be dead. The usual reason to
    # reset a password is that somebody else has it; leaving their session alive
    # makes the reset a formality.
    $rRevoked = Invoke-ExpectingFailure { Invoke-RestMethod -Uri "$ApiBase/auth/session" -Method Get -WebSession $preResetSession }
    Assert-That 'the session opened before the reset was revoked' ($rRevoked.Status -eq 401) "got HTTP $($rRevoked.Status)"
}

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
