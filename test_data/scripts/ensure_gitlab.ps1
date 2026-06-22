# 探测并在需要时启动本地 GitLab（不使用 Docker）
param(
    [string]$Url = "",
    [switch]$NoStart,
    [int]$MaxAttempts = 60,
    [int]$IntervalSeconds = 10
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$StartScript = Join-Path $RepoRoot "test_data\scripts\start_gitlab.ps1"

function Import-GitLabEnv {
    $envFile = Join-Path $RepoRoot "evn\.env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#=]+)=(.*)$') {
                $k = $matches[1].Trim()
                $v = $matches[2].Trim()
                if (-not [Environment]::GetEnvironmentVariable($k, 'Process') -and $v) {
                    [Environment]::SetEnvironmentVariable($k, $v, 'Process')
                }
            }
        }
    }
    foreach ($scope in @('User', 'Machine')) {
        $val = [Environment]::GetEnvironmentVariable('GITLAB_URL', $scope)
        if ($val) { [Environment]::SetEnvironmentVariable('GITLAB_URL', $val, 'Process') }
    }
}

function Test-GitLabReady {
    param([string]$TargetUrl)
    try {
        $r = Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch {
        return $false
    }
}

Import-GitLabEnv
if (-not $Url) {
    if ($env:GITLAB_URL) { $Url = $env:GITLAB_URL } else { $Url = "http://localhost:8000" }
}

Write-Host "Checking GitLab at $Url (Rancher Desktop + compose)"
if (Test-GitLabReady -TargetUrl $Url) {
    Write-Host "GitLab ready at $Url"
    exit 0
}

if ($NoStart) {
    Write-Host "GitLab not ready at $Url (-NoStart)." -ForegroundColor Yellow
    exit 1
}

Write-Host "GitLab not reachable; invoking start_gitlab.ps1 ..."
$prevEa = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $StartScript
$startExit = $LASTEXITCODE
$ErrorActionPreference = $prevEa
if ($startExit -ne 0) {
    exit $startExit
}

for ($i = 1; $i -le $MaxAttempts; $i++) {
    if (Test-GitLabReady -TargetUrl $Url) {
        Write-Host "GitLab ready at $Url (attempt $i)"
        exit 0
    }
    Write-Host "Waiting for GitLab... ($i/$MaxAttempts)"
    if ($i -lt $MaxAttempts) { Start-Sleep -Seconds $IntervalSeconds }
}

Write-Host "GitLab still not ready at $Url." -ForegroundColor Yellow
Write-Host "See evn/gitlab/README.md (Rancher + start.ps1)"
exit 1
