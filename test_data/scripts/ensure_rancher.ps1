# 确保 Rancher Desktop 容器引擎就绪（L3 验收自动调用，非 Docker Desktop）
param(
    [int]$MaxAttempts = 60,
    [int]$IntervalSeconds = 5
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Import-RancherEnv {
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
        foreach ($name in @('RANCHER_RDCTL', 'RANCHER_DOCKER_BIN')) {
            $val = [Environment]::GetEnvironmentVariable($name, $scope)
            if ($val) {
                [Environment]::SetEnvironmentVariable($name, $val, 'Process')
            }
        }
    }
}

function Get-RdctlPath {
    if ($env:RANCHER_RDCTL -and (Test-Path $env:RANCHER_RDCTL)) {
        return $env:RANCHER_RDCTL
    }
    $default = "C:\Program Files\Rancher Desktop\resources\resources\win32\bin\rdctl.exe"
    if (Test-Path $default) { return $default }
    $cmd = Get-Command rdctl -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Add-RancherDockerToPath {
    $bin = if ($env:RANCHER_DOCKER_BIN) {
        $env:RANCHER_DOCKER_BIN
    } else {
        Join-Path $env:USERPROFILE ".rd\bin"
    }
    if (Test-Path $bin) {
        $env:PATH = "$bin;$env:PATH"
    }
    $win32Bin = "C:\Program Files\Rancher Desktop\resources\resources\win32\bin"
    if ((Test-Path $win32Bin) -and ($env:PATH -notlike "*$win32Bin*")) {
        $env:PATH = "$win32Bin;$env:PATH"
    }
}

function Test-DockerReady {
    Add-RancherDockerToPath
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        & docker version 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prev
    }
}

Import-RancherEnv
Add-RancherDockerToPath

if (Test-DockerReady) {
    Write-Host "Rancher docker engine already ready"
    exit 0
}

$rdctl = Get-RdctlPath
if (-not $rdctl) {
    Write-Host "rdctl not found. Install Rancher Desktop or set RANCHER_RDCTL." -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting Rancher Desktop (background, moby, no k8s)..."
& $rdctl start `
    --application.start-in-background `
    --container-engine.name=moby `
    --kubernetes.enabled=false
if ($LASTEXITCODE -ne 0) {
    Write-Host "rdctl start failed (exit $LASTEXITCODE)" -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host "Waiting for docker engine (up to $($MaxAttempts * $IntervalSeconds)s)..."
for ($i = 1; $i -le $MaxAttempts; $i++) {
    if (Test-DockerReady) {
        Write-Host "Rancher docker engine ready (attempt $i)"
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        & docker version 2>&1 | Select-Object -First 4
        $ErrorActionPreference = $prev
        exit 0
    }
    Write-Host "Waiting for docker... ($i/$MaxAttempts)"
    if ($i -lt $MaxAttempts) { Start-Sleep -Seconds $IntervalSeconds }
}

Write-Host "Docker engine not ready after waiting." -ForegroundColor Yellow
exit 1
