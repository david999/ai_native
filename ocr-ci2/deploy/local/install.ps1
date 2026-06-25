# 本地开发 — Windows 宿主机原生 Gateway（Gateway 不用 Docker）
#
# 逻辑清单：
# - 校验：node、npm、python、git 在 PATH 上（缺失则退出）
# - OCR CLI：`ocr version` 成功则跳过 `npm install -g`（除非 -SkipOcrNpm）
# - 始终：pip install -r gateway/requirements.txt
# - 仅警告：缺少 ~/.opencodereview/config.json（不阻断）
# - 不做：校验 npm 包版本；跳过 pip install；创建 config.json

param(
    [switch]$SkipOcrNpm
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Error "$Name not found on PATH"
    }
}

function Test-OcrCliInstalled {
    if (-not (Get-Command ocr -ErrorAction SilentlyContinue)) {
        return $false
    }
    & ocr version 2>$null
    return $LASTEXITCODE -eq 0
}

Write-Host "Checking prerequisites..."
Require-Command node
Require-Command npm
Require-Command python
Require-Command git

if (-not $SkipOcrNpm) {
    if (Test-OcrCliInstalled) {
        Write-Host "OpenCodeReview CLI already installed; skipping npm install -g"
    } else {
        Write-Host "Installing OpenCodeReview CLI (global npm)..."
        npm install -g @alibaba-group/open-code-review
    }
}

Write-Host "Installing Gateway Python deps..."
Push-Location $Root
try {
    python -m pip install -r gateway/requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

$userCfg = Join-Path $env:USERPROFILE ".opencodereview\config.json"
if (-not (Test-Path $userCfg)) {
    Write-Warning "Missing $userCfg — create it with llm.* and gitlab.api_token before running reviews."
}

Write-Host "OCR CLI:"
& ocr version
Write-Host ""
Write-Host "Next: copy deploy\local\gateway.env.example to deploy\local\gateway.env"
Write-Host "      .\deploy\local\run.ps1"
