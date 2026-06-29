# DEPRECATED — Severity Dashboard 已并入 OCR Gateway :8010
#
# 请改用：
#   .\deploy\local\run.ps1
#   浏览器 http://localhost:8010/
#
# 官方 OCR Viewer（可选）：
#   ocr viewer   # :5483

param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$DeployLocal = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent $DeployLocal)

Write-Warning "run_viewer.ps1 is deprecated. Dashboard is now at http://localhost:8010/ (use deploy\local\run.ps1)."
Write-Host "Forwarding to deploy\local\run.ps1 ..."

& (Join-Path $DeployLocal "run.ps1") @PSBoundParameters
