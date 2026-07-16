# 构建 ocr-gateway Docker 镜像（生产）
#
# 用法（在 ocr-ci2 根目录）：
#   .\deploy\prod\docker\build_image.ps1
#
# 逻辑清单：
# - 校验：python 在 PATH（用于 bake 脚本）
# - Bake：将 -UserConfig / ~/.opencodereview/config.json **原样**写入 .build/config.json（无 defaults 合并）
# - 构建：docker build -f deploy/prod/docker/Dockerfile -t <Tag> .（context=仓库根）
# - 不做：镜像内跳过 OCR npm（Dockerfile 始终 npm install -g）；启动容器

param(
    [string]$Tag = "ocr-gateway:local",
    [string]$UserConfig = "",
    [string]$EnvFile = "",
    [switch]$NoCache,
    [switch]$SkipSecretCheck
)

$ErrorActionPreference = "Stop"
$DockerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $DockerDir))
$BakeScript = Join-Path $Root "scripts\acceptance\bake_ocr_config.py"
$OutConfig = Join-Path $Root ".build\config.json"
$Dockerfile = Join-Path $DockerDir "Dockerfile"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python not found; required to bake config.json"
}

$bakeArgs = @($BakeScript, "-o", $OutConfig)
if ($UserConfig) {
    $bakeArgs += @("--config", (Resolve-Path $UserConfig))
} elseif (Test-Path (Join-Path $env:USERPROFILE ".opencodereview\config.json")) {
    Write-Host "Baking from user config: $env:USERPROFILE\.opencodereview\config.json"
    $bakeArgs += @("--from-user-config")
} else {
    Write-Error "Provide -UserConfig path or create $env:USERPROFILE\.opencodereview\config.json"
}
if ($EnvFile) {
    $bakeArgs += @("--env-file", (Resolve-Path $EnvFile))
}
if (-not $SkipSecretCheck) {
    $bakeArgs += @("--require-secrets")
}

Write-Host "Baking config.json ..."
& python @bakeArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$buildArgs = @("build", "-f", $Dockerfile, "-t", $Tag, ".")
if ($NoCache) { $buildArgs += "--no-cache" }

Push-Location $Root
try {
    Write-Host "docker build -f deploy/prod/docker/Dockerfile -t $Tag ."
    docker @buildArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host "Done. Start: .\deploy\prod\docker\run.ps1"
Write-Host "Health: curl http://localhost:8010/health"
exit 0
