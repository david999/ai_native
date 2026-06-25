# Severity Dashboard — 本地开发（Windows）
#
# 用法：
#   copy deploy\local\viewer.env.example deploy\local\viewer.env
#   .\deploy\local\run_viewer.ps1
#
# 需同时运行官方 viewer（可选，用于「官方详情」链接）：
#   ocr viewer   # :5483

param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$DeployLocal = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent $DeployLocal)
if (-not $EnvFile) {
    $EnvFile = Join-Path $DeployLocal "viewer.env"
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
    Write-Warning "No $EnvFile — using defaults (see deploy\local\viewer.env.example)"
}

$env:PYTHONPATH = $Root
$port = if ($env:SEVERITY_VIEWER_PORT) { $env:SEVERITY_VIEWER_PORT } else { "5484" }
$hostName = if ($env:SEVERITY_VIEWER_HOST) { $env:SEVERITY_VIEWER_HOST } else { "127.0.0.1" }

Write-Host "Starting Severity Dashboard on http://localhost:${port} (Ctrl+C to stop)"
Write-Host "Official OCR Viewer (optional): ocr viewer -> http://localhost:5483"

Set-Location $Root
python -m viewer.app --host $hostName --port $port
