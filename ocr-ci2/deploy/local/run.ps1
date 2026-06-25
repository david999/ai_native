# 在宿主机运行 OCR Gateway — 本地开发（Windows）
#
# 用法：
#   .\deploy\local\install.ps1
#   copy deploy\local\gateway.env.example deploy\local\gateway.env
#   .\deploy\local\run.ps1
#
# 逻辑清单：
# - 加载：deploy/local/gateway.env（KEY=VALUE，# 行注释跳过）
# - 校验：OCR_GATEWAY_SECRET 必填（加载 env 后未设置则退出）
# - 默认：PYTHONPATH=仓库根、OCR_POST_SCRIPT、OCR_GATEWAY_WORK_ROOT=.gateway-work
# - 不做：校验 ocr 是否在 PATH；校验 GitLab 可达；后台守护进程

param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$DeployLocal = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent $DeployLocal)
if (-not $EnvFile) {
    $EnvFile = Join-Path $DeployLocal "gateway.env"
}

if (Test-Path $EnvFile) {
    Write-Host "Loading env from $EnvFile"
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        if ($line -match '^\s*([^#=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
} else {
    Write-Warning "No $EnvFile — using defaults (see deploy\local\gateway.env.example)"
}

if (-not $env:OCR_GATEWAY_SECRET) {
    Write-Error "OCR_GATEWAY_SECRET is required. Set it in deploy\local\gateway.env"
}

if (-not (Get-Command ocr -ErrorAction SilentlyContinue)) {
    Write-Warning "ocr CLI not in PATH. Gateway needs 'ocr review' (npm global bin). Install: deploy\local\install.ps1"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Warning "git not in PATH. Gateway clone/fetch will fail."
}

$env:PYTHONPATH = $Root
if (-not $env:OCR_POST_SCRIPT) {
    $env:OCR_POST_SCRIPT = Join-Path $Root "scripts\post_ocr_to_gitlab.py"
}
if (-not $env:OCR_GATEWAY_WORK_ROOT) {
    $env:OCR_GATEWAY_WORK_ROOT = Join-Path $Root ".gateway-work"
}

$port = if ($env:OCR_GATEWAY_PORT) { $env:OCR_GATEWAY_PORT } else { "8010" }
Write-Host "Starting OCR Gateway on http://0.0.0.0:${port} (Ctrl+C to stop)"
Write-Host "Health: http://localhost:${port}/health"
Write-Host "CI should use OCR_GATEWAY_URL=http://host.docker.internal:${port}"

Push-Location $Root
try {
    python -m uvicorn gateway.main:app --host 0.0.0.0 --port $port
} finally {
    Pop-Location
}
