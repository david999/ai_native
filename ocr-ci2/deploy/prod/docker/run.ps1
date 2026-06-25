# 通过 docker compose 运行 OCR Gateway（生产 Docker）
#
# 逻辑清单：
# - 可选：-Build 先执行 build_image.ps1
# - 启动：docker compose -f deploy/prod/docker/docker-compose.yml up -d
# - 不做：校验镜像是否存在；配置 GitLab 网络（见 compose 文件）

param(
    [switch]$Build
)

$DockerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $DockerDir))
$ComposeFile = Join-Path $DockerDir "docker-compose.yml"

Push-Location $Root
try {
    if ($Build) {
        & (Join-Path $DockerDir "build_image.ps1")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    docker compose -f $ComposeFile up -d
    Write-Host "OCR Gateway: http://localhost:8010/health"
} finally {
    Pop-Location
}
