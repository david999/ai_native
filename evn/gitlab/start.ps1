# 通过 Rancher Desktop 的 docker compose 启动 GitLab CE（复用 data/config/logs）
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

function Import-GitLabImageEnv {
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
        $val = [Environment]::GetEnvironmentVariable('GITLAB_IMAGE_MIRROR', $scope)
        if ($val) { [Environment]::SetEnvironmentVariable('GITLAB_IMAGE_MIRROR', $val, 'Process') }
    }
}

function Test-GitLabImagePresent {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        docker image inspect gitlab/gitlab-ce:latest 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Ensure-GitLabImage {
    if (Test-GitLabImagePresent) {
        Write-Host "gitlab/gitlab-ce:latest already present"
        return
    }
    $mirror = if ($env:GITLAB_IMAGE_MIRROR) {
        $env:GITLAB_IMAGE_MIRROR
    } else {
        "docker.m.daocloud.io/gitlab/gitlab-ce:latest"
    }
    Write-Host "Pulling gitlab/gitlab-ce:latest ..."
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    docker pull gitlab/gitlab-ce:latest 2>&1 | Write-Host
    $ErrorActionPreference = $prev
    if ($LASTEXITCODE -eq 0) { return }
    Write-Host "Docker Hub pull failed; trying mirror: $mirror"
    docker pull $mirror
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    docker tag $mirror gitlab/gitlab-ce:latest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Import-GitLabImageEnv
Ensure-GitLabImage

Write-Host "Creating docker network gitlab_default (if missing)..."
$prevEa = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
docker network create gitlab_default 2>$null | Out-Null
$ErrorActionPreference = $prevEa

Write-Host "Starting GitLab CE via compose in $GitLabDir ..."
Push-Location $GitLabDir
try {
    docker compose up -d gitlab
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host "GitLab container start requested (warm-up may take several minutes)"
exit 0
