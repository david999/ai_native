# 探测并在需要时通过 Docker Compose 启动本地 GitLab（L3 用）
param(
    [string]$Url = "",
    [switch]$NoStart,
    [int]$MaxAttempts = 36,
    [int]$IntervalSeconds = 10
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ComposeDir = Join-Path $RepoRoot "evn\gitlab"

if (-not $Url) {
    if ($env:GITLAB_URL) { $Url = $env:GITLAB_URL } else { $Url = "http://localhost:8000" }
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

function Get-DockerCommand {
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Start-GitLabDocker {
    param([string]$DockerExe, [string]$ComposePath)
    Write-Host "Starting GitLab via Docker Compose ($ComposePath)..."
    $networkExists = & $DockerExe network inspect gitlab_default 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Creating docker network gitlab_default"
        & $DockerExe network create gitlab_default | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to create docker network gitlab_default" }
    }
    Push-Location $ComposePath
    try {
        & $DockerExe compose up -d gitlab
        if ($LASTEXITCODE -ne 0) { throw "docker compose up failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    Write-Host "GitLab container starting (first boot may take several minutes)..."
}

Write-Host "Checking GitLab at $Url"
if (Test-GitLabReady -TargetUrl $Url) {
    Write-Host "GitLab ready at $Url"
    exit 0
}

if ($NoStart) {
    Write-Host "GitLab not ready at $Url (-NoStart: will not start Docker)." -ForegroundColor Yellow
    exit 1
}

$docker = Get-DockerCommand
if (-not $docker) {
    Write-Host "GitLab not reachable and Docker CLI not found." -ForegroundColor Yellow
    Write-Host "Install Docker Desktop (or add docker to PATH), or start GitLab manually at $Url"
    Write-Host "Compose file: $ComposeDir\docker-compose.yml"
    exit 1
}

if (-not (Test-Path (Join-Path $ComposeDir "docker-compose.yml"))) {
    throw "Missing compose file: $ComposeDir\docker-compose.yml"
}

Start-GitLabDocker -DockerExe $docker -ComposePath $ComposeDir

for ($i = 1; $i -le $MaxAttempts; $i++) {
    if (Test-GitLabReady -TargetUrl $Url) {
        Write-Host "GitLab ready at $Url (attempt $i)"
        exit 0
    }
    Write-Host "Waiting for GitLab... ($i/$MaxAttempts)"
    if ($i -lt $MaxAttempts) { Start-Sleep -Seconds $IntervalSeconds }
}

Write-Host "GitLab still not ready at $Url after docker compose up." -ForegroundColor Yellow
Write-Host "Check: docker logs gitlab"
exit 1
