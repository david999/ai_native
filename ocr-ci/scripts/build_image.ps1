# Build ocr-ci Docker image from ~/.opencodereview/config.json (single config source).
#
# Job runtime priority:
#   OCR LLM:  env OCR_LLM_*  >  /root/.opencodereview/config.json
#   GitLab:   env GITLAB_API_TOKEN  >  config.json gitlab.api_token  >  CI_JOB_TOKEN
#
# Usage:
#   .\scripts\build_image.ps1
#   .\scripts\build_image.ps1 -UserConfig C:\Users\you\.opencodereview\config.json
#   .\scripts\build_image.ps1 -SkipSecretCheck   # defaults-only trial (not for production)

param(
    [string]$Tag = "ocr-ci:local",
    [string]$UserConfig = "",
    [string]$EnvFile = "",
    [switch]$NoCache,
    [switch]$SkipSecretCheck
)

$ErrorActionPreference = "Stop"
$OcrCiDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BakeScript = Join-Path $OcrCiDir "scripts\acceptance\bake_ocr_config.py"
$OutConfig = Join-Path $OcrCiDir ".build\config.json"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python not found; required to bake config.json"
}

$bakeArgs = @($BakeScript, "-o", $OutConfig)
if ($UserConfig) {
    $bakeArgs += @("--config", (Resolve-Path $UserConfig))
} else {
    $defaultUserConfig = Join-Path $env:USERPROFILE ".opencodereview\config.json"
    if (Test-Path $defaultUserConfig) {
        Write-Host "Baking from user config: $defaultUserConfig"
        $bakeArgs += @("--from-user-config")
    } else {
        Write-Warning "Missing $defaultUserConfig — baking repo defaults only"
    }
}
if ($EnvFile) {
    Write-Host "Also merging env file: $EnvFile"
    $bakeArgs += @("--env-file", (Resolve-Path $EnvFile))
}
if (-not $SkipSecretCheck) {
    $bakeArgs += @("--require-secrets")
}

Write-Host "Baking config.json ..."
& python @bakeArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$buildArgs = @("build", "-t", $Tag, ".")
if ($NoCache) { $buildArgs += "--no-cache" }

Push-Location $OcrCiDir
try {
    Write-Host "docker build -t $Tag ."
    docker @buildArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host "Done. Verify: docker run --rm $Tag ocr version"
exit 0
