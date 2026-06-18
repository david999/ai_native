# 启动 GitLab Runner 容器（Docker executor，L3b 用）
# Docker Hub 不可达时从 GITLAB_RUNNER_IMAGE_MIRROR 拉取并 tag 为 gitlab/gitlab-runner:latest
$ErrorActionPreference = "Stop"
$GitLabDir = $PSScriptRoot
$EnsureRancher = Join-Path (Split-Path -Parent (Split-Path -Parent $GitLabDir)) "test_data\scripts\ensure_rancher.ps1"

function Add-RancherDockerToPath {
    $bin = if ($env:RANCHER_DOCKER_BIN) {
        $env:RANCHER_DOCKER_BIN
    } else {
        Join-Path $env:USERPROFILE ".rd\bin"
    }
    if (Test-Path $bin) { $env:PATH = "$bin;$env:PATH" }
    $win32Bin = "C:\Program Files\Rancher Desktop\resources\resources\win32\bin"
    if ((Test-Path $win32Bin) -and ($env:PATH -notlike "*$win32Bin*")) {
        $env:PATH = "$win32Bin;$env:PATH"
    }
}

if (Test-Path $EnsureRancher) {
    & $EnsureRancher
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Add-RancherDockerToPath
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "docker not found; run test_data/scripts/ensure_rancher.ps1 first"
        exit 1
    }
}

Add-RancherDockerToPath

function Import-RunnerImageEnv {
    $envFile = Join-Path (Split-Path -Parent $GitLabDir) ".env"
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
        foreach ($name in @('GITLAB_RUNNER_IMAGE_MIRROR', 'GITLAB_IMAGE_MIRROR')) {
            $val = [Environment]::GetEnvironmentVariable($name, $scope)
            if ($val) { [Environment]::SetEnvironmentVariable($name, $val, 'Process') }
        }
    }
}

function Test-RunnerImagePresent {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        docker image inspect gitlab/gitlab-runner:latest 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Ensure-RunnerImage {
    if (Test-RunnerImagePresent) {
        Write-Host "gitlab/gitlab-runner:latest already present"
        return
    }
    $mirror = if ($env:GITLAB_RUNNER_IMAGE_MIRROR) {
        $env:GITLAB_RUNNER_IMAGE_MIRROR
    } elseif ($env:GITLAB_IMAGE_MIRROR) {
        # 若只配了 CE 镜像，尝试同 registry 下的 runner
        $env:GITLAB_IMAGE_MIRROR -replace '/gitlab-ce:', '/gitlab-runner:'
    } else {
        "docker.m.daocloud.io/gitlab/gitlab-runner:latest"
    }
    Write-Host "Pulling gitlab/gitlab-runner:latest ..."
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    docker pull gitlab/gitlab-runner:latest 2>&1 | Write-Host
    $ErrorActionPreference = $prev
    if ($LASTEXITCODE -eq 0) { return }
    Write-Host "Docker Hub pull failed; trying mirror: $mirror"
    docker pull $mirror
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    docker tag $mirror gitlab/gitlab-runner:latest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$configDir = Join-Path (Split-Path -Parent $GitLabDir) "gitlab-runner\config"
if (-not (Test-Path (Join-Path $configDir "config.toml"))) {
    Write-Warning "Missing $configDir\config.toml — register runner first (see evn/gitlab/README.md)"
}

Import-RunnerImageEnv
Ensure-RunnerImage

Write-Host "Creating docker network gitlab_default (if missing)..."
$prevEa = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
docker network create gitlab_default 2>$null | Out-Null
$ErrorActionPreference = $prevEa

Write-Host "Starting gitlab-runner via compose in $GitLabDir ..."
Push-Location $GitLabDir
try {
    docker compose up -d gitlab-runner
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host "gitlab-runner container start requested"
Write-Host "Check: docker ps --filter name=gitlab-runner"
Write-Host "Logs:  docker logs gitlab-runner --tail 30"
exit 0
