# 启动本机 GitLab：Rancher Desktop + evn/gitlab compose（非 Docker Desktop）
param(
    [string]$Url = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EnsureRancher = Join-Path $RepoRoot "test_data\scripts\ensure_rancher.ps1"
$HookScript = Join-Path $RepoRoot "evn\gitlab\start.ps1"

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
        foreach ($name in @('GITLAB_URL', 'GITLAB_START_COMMAND')) {
            $val = [Environment]::GetEnvironmentVariable($name, $scope)
            if ($val) {
                [Environment]::SetEnvironmentVariable($name, $val, 'Process')
            }
        }
    }
}

Import-GitLabEnv
if (-not $Url) {
    if ($env:GITLAB_URL) { $Url = $env:GITLAB_URL } else { $Url = "http://localhost:8000" }
}

# 高级覆盖：显式 GITLAB_START_COMMAND 跳过默认 Rancher 链路
if ($env:GITLAB_START_COMMAND) {
    Write-Host "Running GITLAB_START_COMMAND (override)..."
    Invoke-Expression $env:GITLAB_START_COMMAND
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    exit 0
}

Write-Host "Ensuring Rancher Desktop docker engine..."
& $EnsureRancher
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path $HookScript) {
    Write-Host "Running $HookScript ..."
    & $HookScript
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    exit 0
}

Write-Host "Missing evn/gitlab/start.ps1" -ForegroundColor Yellow
exit 1
