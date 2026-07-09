# OCR Gateway + datacalc-web E2E 入口
param(
    [string]$Scenario = "",
    [switch]$All,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"
$E2eRoot = $PSScriptRoot

if (-not $All -and -not $Scenario) {
    Write-Host "Usage: .\run_e2e.ps1 -Scenario D01_feature_date_guard" -ForegroundColor Yellow
    Write-Host "       .\run_e2e.ps1 -All [-SkipPreflight]" -ForegroundColor Yellow
    exit 2
}

$pyArgs = @("$E2eRoot\run_e2e.py")
if ($All) { $pyArgs += "--all" }
if ($Scenario) { $pyArgs += @("--scenario", $Scenario) }
if ($SkipPreflight) { $pyArgs += "--skip-preflight" }

Push-Location $E2eRoot
try {
    & python @pyArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
