# How this repo talks to Docker.
#
# ADR 0006 chose Docker Desktop; what is actually installed is **Docker Engine
# inside WSL2 Ubuntu** (ADR 0007). Docker Desktop's installer needs UAC and
# could not be run from an automated session, whereas root inside WSL needs no
# password at all.
#
# The consequence is that `docker` is not on the Windows PATH, so every call is
# routed through `wsl -d Ubuntu -u root`, translating `D:\...` to `/mnt/d/...`.
# If Docker Desktop is ever installed, `Get-DockerMode` returns 'native' and
# every caller works unchanged — which is why this lives in one file rather than
# `wsl` being sprinkled through the scripts.
#
# **Two entry points, deliberately separate.** An earlier version had a single
# function that both emitted output and returned an exit code; callers capturing
# its output got the exit code mixed in, and `verify.ps1` consequently reported
# the wrong database backend — the exact failure that check exists to catch. So:
#
#   Invoke-Docker    — for commands you want to *see*. Prints; returns exit code.
#   Get-DockerOutput — for commands you want to *read*. Returns stdout lines only.

$script:WslDistro = 'Ubuntu'

function Get-DockerMode {
    if (Get-Command docker -ErrorAction SilentlyContinue) { return 'native' }
    $probe = & wsl.exe -d $script:WslDistro -u root -- bash -lc 'command -v docker >/dev/null 2>&1 && echo yes' 2>$null
    if ($probe -match 'yes') { return 'wsl' }
    return 'none'
}

function Convert-ToWslPath {
    param([Parameter(Mandatory = $true)][string]$WindowsPath)
    $full = (Resolve-Path -LiteralPath $WindowsPath).Path
    $drive = $full.Substring(0, 1).ToLower()
    $rest = $full.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

function Assert-Docker {
    if ((Get-DockerMode) -ne 'none') { return }
    Write-Host 'Docker is not available on Windows or in WSL.' -ForegroundColor Red
    Write-Host 'Docker Engine in WSL needs no UAC (ADR 0007):' -ForegroundColor Yellow
    Write-Host '  wsl -d Ubuntu -u root -- apt-get install -y docker.io docker-compose-v2'
    exit 1
}

function script:BuildDockerCall {
    param([string]$Arguments, [string]$WorkingDirectory)
    if ((Get-DockerMode) -eq 'native') {
        return @{ exe = 'docker'; args = ($Arguments -split ' '); cwd = $WorkingDirectory }
    }
    $cd = ''
    if ($WorkingDirectory) { $cd = "cd '$(Convert-ToWslPath $WorkingDirectory)' && " }
    return @{
        exe  = 'wsl.exe'
        args = @('-d', $script:WslDistro, '-u', 'root', '--', 'bash', '-lc', "$cd docker $Arguments")
        cwd  = $null
    }
}

function Get-DockerOutput {
    <#
      Returns stdout lines and nothing else, so a caller can parse them.
      Native stderr is merged in because docker writes progress there; callers
      wanting a single value should take the last non-empty line.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Arguments,
        [string]$WorkingDirectory
    )
    Assert-Docker
    $call = script:BuildDockerCall -Arguments $Arguments -WorkingDirectory $WorkingDirectory

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($call.cwd) { Push-Location $call.cwd }
        try {
            $out = & $call.exe @($call.args) 2>&1 | ForEach-Object { "$_" }
        } finally { if ($call.cwd) { Pop-Location } }
        return @($out | Where-Object { $_ -and $_.Trim() })
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Invoke-Docker {
    <# Prints output to the host and returns the exit code. #>
    param(
        [Parameter(Mandatory = $true)][string]$Arguments,
        [string]$WorkingDirectory
    )
    Assert-Docker
    $call = script:BuildDockerCall -Arguments $Arguments -WorkingDirectory $WorkingDirectory

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($call.cwd) { Push-Location $call.cwd }
        try {
            & $call.exe @($call.args) 2>&1 | ForEach-Object { Write-Host $_ }
            return $LASTEXITCODE
        } finally { if ($call.cwd) { Pop-Location } }
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Get-DockerContainerHealth {
    <# 'healthy' | 'starting' | 'unhealthy' | 'missing' #>
    param([string]$Name = 'nexus-db')
    if ((Get-DockerMode) -eq 'none') { return 'missing' }
    $out = Get-DockerOutput -Arguments "inspect --format '{{.State.Health.Status}}' $Name"
    $last = @($out) | Select-Object -Last 1
    if (-not $last -or $last -match 'No such object|Error') { return 'missing' }
    return $last.Trim()
}

function Start-DockerDaemon {
    <# WSL has no systemd session by default, so the daemon needs starting after
       a WSL restart. Idempotent. #>
    if ((Get-DockerMode) -ne 'wsl') { return }
    & wsl.exe -d $script:WslDistro -u root -- bash -lc `
        'docker info >/dev/null 2>&1 || (systemctl start docker 2>/dev/null || service docker start >/dev/null 2>&1); sleep 2' 2>$null | Out-Null
}
