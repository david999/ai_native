param(
    [Parameter(Mandatory = $true)][int]$ProjectId,
    [Parameter(Mandatory = $true)][int]$MrIid,
    [string]$BaseUrl = "http://localhost:8001",
    [string]$SystemTemplate = "",
    [switch]$ForceFull,
    [string]$ReportJson = "",
    [ValidateSet("direct", "gate")]
    [string]$Mode = "direct"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EnvFile = Join-Path $RepoRoot "evn\.env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $k = $matches[1].Trim()
            $v = $matches[2].Trim()
            $existing = [Environment]::GetEnvironmentVariable($k)
            if ([string]::IsNullOrEmpty($existing)) {
                [Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }
}

$body = @{
    project_id = $ProjectId
    mr_iid     = $MrIid
    force_full = [bool]$ForceFull
}
if ($SystemTemplate) { $body.system_template = $SystemTemplate }
$jsonBody = $body | ConvertTo-Json

$headers = @{ "Content-Type" = "application/json" }
if ($env:REVIEW_API_SECRET) {
    $headers["X-AICR-Secret"] = $env:REVIEW_API_SECRET
}

if ($Mode -eq "gate") {
    $env:CI_PROJECT_ID = "$ProjectId"
    $env:CI_MERGE_REQUEST_IID = "$MrIid"
    $env:AICR_REVIEW_URL = $BaseUrl
    if ($env:REVIEW_API_SECRET) { $env:AICR_REVIEW_SECRET = $env:REVIEW_API_SECRET }
    $gate = Join-Path $RepoRoot "aicr-reviewer\scripts\ci_review_gate.sh"
    if (Get-Command bash -ErrorAction SilentlyContinue) {
        bash $gate
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) { exit $LASTEXITCODE }
    } else {
        Write-Warning "bash not found; falling back to direct POST"
        $Mode = "direct"
    }
}

if ($Mode -eq "direct") {
    $uri = "$($BaseUrl.TrimEnd('/'))/review"
    try {
        $resp = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $jsonBody -TimeoutSec 600
    } catch {
        Write-Error $_
        exit 1
    }
    $out = $resp | ConvertTo-Json -Depth 20
    Write-Host $out
    if ($ReportJson) {
        $dir = Split-Path -Parent $ReportJson
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $resp | Add-Member -NotePropertyName trigger -NotePropertyValue direct -Force
        if ($SystemTemplate) { $resp | Add-Member -NotePropertyName system_template_requested -NotePropertyValue $SystemTemplate -Force }
        $resp | ConvertTo-Json -Depth 20 | Set-Content -Path $ReportJson -Encoding UTF8
        Write-Host "Report written to $ReportJson"
    }
}
