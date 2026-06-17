# 本地启动 aicr-reviewer（无需 Docker）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python not found. Install Python 3.10+ and retry."
}

$venv = Join-Path $Root ".venv"
if (-not (Test-Path $venv)) {
    python -m venv $venv
}
& "$venv\Scripts\python.exe" -m pip install -q -r requirements.txt

$env:GITLAB_URL = if ($env:GITLAB_URL) { $env:GITLAB_URL } else { "http://localhost:8000" }
Write-Host "Starting AICR Reviewer at http://localhost:8001 (GITLAB_URL=$env:GITLAB_URL)"
& "$venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
