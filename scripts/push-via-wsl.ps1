[CmdletBinding()]
param(
    [string]$Remote = "origin",
    [string]$Branch,
    [string]$Distro = "Ubuntu",
    [ValidateRange(1, 5)]
    [int]$Attempts = 3,
    [ValidateRange(10, 300)]
    [int]$TimeoutSeconds = 90,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$traceVariables = @(
    "GH_DEBUG",
    "GIT_CURL_VERBOSE",
    "GIT_TRACE",
    "GIT_TRACE_CURL",
    "GIT_TRACE_PACKET",
    "GIT_TRACE_PERFORMANCE",
    "GIT_TRACE_SETUP",
    "GIT_TRACE_SHALLOW",
    "GIT_TRACE2",
    "GIT_TRACE2_EVENT",
    "GIT_TRACE2_PERF"
)
foreach ($variable in $traceVariables) {
    [Environment]::SetEnvironmentVariable($variable, $null, "Process")
}

function ConvertTo-BashSingleQuoted {
    param([Parameter(Mandatory)][string]$Value)

    return "'" + $Value.Replace("'", "'`"`"'`"`'") + "'"
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $output = & $Executable @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE"
    }
    return ($output | Out-String).Trim()
}

if (-not $IsWindows) {
    throw "This helper must run from Windows PowerShell or PowerShell 7."
}

$git = (Get-Command git -ErrorAction Stop).Source
$gh = (Get-Command gh -ErrorAction Stop).Source
$wsl = (Get-Command wsl.exe -ErrorAction Stop).Source

$repoRoot = Invoke-CheckedCommand $git @("rev-parse", "--show-toplevel")
if (-not $Branch) {
    $Branch = Invoke-CheckedCommand $git @("branch", "--show-current")
}
if (-not $Branch) {
    throw "Detached HEAD is not supported; pass -Branch explicitly."
}
& $git check-ref-format --branch $Branch *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Invalid Git branch name."
}
if ($Remote -notmatch "^[A-Za-z0-9._-]+$") {
    throw "Remote must contain only letters, numbers, dot, underscore, or hyphen."
}

$remoteUrl = Invoke-CheckedCommand $git @("remote", "get-url", $Remote)
if ($remoteUrl -notmatch "^https://github\.com/[^/]+/[^/]+(?:\.git)?$") {
    throw "Remote must be a credential-free GitHub HTTPS URL."
}

& $gh auth status --hostname github.com *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Windows gh is not authenticated for github.com."
}

$wslRepo = Invoke-CheckedCommand $wsl @(
    "-d",
    $Distro,
    "--",
    "wslpath",
    "-a",
    $repoRoot
)
$wslGh = Invoke-CheckedCommand $wsl @(
    "-d",
    $Distro,
    "--",
    "wslpath",
    "-a",
    $gh
)

$credentialHelper = "!`"$wslGh`" auth git-credential"
$pushArguments = @(
    "git",
    "-c",
    "credential.helper=",
    "-c",
    "credential.helper=$credentialHelper",
    "push"
)
if ($DryRun) {
    $pushArguments += "--dry-run"
}
$pushArguments += @(
    "--set-upstream",
    $Remote,
    "HEAD:refs/heads/$Branch"
)

$quotedArguments = $pushArguments | ForEach-Object {
    ConvertTo-BashSingleQuoted $_
}
$unsetTrace = "unset " + ($traceVariables -join " ")
$bashCommand = "$unsetTrace; cd $(ConvertTo-BashSingleQuoted $wslRepo) && " +
    "timeout --foreground ${TimeoutSeconds}s " +
    ($quotedArguments -join " ")

for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    $output = & $wsl -d $Distro -- bash -lc $bashCommand 2>&1
    if ($LASTEXITCODE -eq 0) {
        if ($output) {
            $output | Write-Output
        }
        $mode = if ($DryRun) { "dry-run" } else { "push" }
        Write-Output "WSL Git $mode succeeded on attempt $attempt/$Attempts."
        exit 0
    }

    Write-Warning "WSL Git attempt $attempt/$Attempts failed with exit code $LASTEXITCODE."
    if ($attempt -lt $Attempts) {
        Start-Sleep -Seconds ([Math]::Min(2 * $attempt, 6))
    }
}

throw (
    "WSL Git exhausted $Attempts attempts. " +
    "Do not retry Windows Git automatically; diagnose the WSL route or use " +
    "the explicit Git Data API fallback."
)
