# GitLab CI 门禁 PowerShell 版（与 ci_review_gate.sh 语义一致）
param(
    [string]$Url = $env:AICR_REVIEW_URL,
    [int]$ProjectId = 0,
    [int]$MrIid = 0,
    [string]$Secret = $env:AICR_REVIEW_SECRET,
    [int]$Threshold = 0,
    [double]$CachedScore = -1,
    [bool]$CachedCompleted = $false
)

$ErrorActionPreference = "Stop"

if (-not $Url) { $Url = "http://localhost:8001" }
if (-not $ProjectId) {
    if ($env:CI_PROJECT_ID) { $ProjectId = [int]$env:CI_PROJECT_ID }
    elseif ($env:AICR_PROJECT_ID) { $ProjectId = [int]$env:AICR_PROJECT_ID }
}
if (-not $MrIid) {
    if ($env:CI_MERGE_REQUEST_IID) { $MrIid = [int]$env:CI_MERGE_REQUEST_IID }
    elseif ($env:AICR_MR_IID) { $MrIid = [int]$env:AICR_MR_IID }
}
if (-not $Threshold) {
    if ($env:AICR_SCORE_THRESHOLD) { $Threshold = [int]$env:AICR_SCORE_THRESHOLD }
    else { $Threshold = 60 }
}

function Pass-Job([string]$Reason) {
    Write-Host "AICR gate: MR passes — $Reason"
    exit 0
}

function Fail-Job([string]$Reason) {
    Write-Host "AICR gate: MR blocked — $Reason"
    exit 1
}

function Evaluate-Gate([bool]$Completed, $Score) {
    Write-Host "AICR response: review_completed=$Completed score=$Score"
    if (-not $Completed) {
        Pass-Job "review not completed"
    }
    if ($null -eq $Score -or "$Score" -eq "") {
        Pass-Job "missing score"
    }
    $scoreNum = [double]$Score
    if ($scoreNum -lt $Threshold) {
        Fail-Job "score $scoreNum < threshold $Threshold"
    }
    Pass-Job "score $scoreNum >= threshold $Threshold"
}

if ($ProjectId -le 0 -or $MrIid -le 0) {
    Pass-Job "missing project_id or mr_iid"
}

if ($CachedScore -ge 0) {
    Evaluate-Gate -Completed $CachedCompleted -Score $CachedScore
}

$body = @{ project_id = $ProjectId; mr_iid = $MrIid } | ConvertTo-Json
$headers = @{ "Content-Type" = "application/json" }
if ($Secret) { $headers["X-AICR-Secret"] = $Secret }

try {
    $resp = Invoke-WebRequest -Uri "$($Url.TrimEnd('/'))/review" `
        -Method POST -Body $body -Headers $headers `
        -UseBasicParsing -TimeoutSec $(if ($env:AICR_REVIEW_TIMEOUT) { [int]$env:AICR_REVIEW_TIMEOUT } else { 300 })
} catch {
    $status = $null
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
    Pass-Job "request failed or HTTP $status"
}

if ($resp.StatusCode -ne 200) {
    Pass-Job "HTTP $($resp.StatusCode)"
}

try {
    $data = $resp.Content | ConvertFrom-Json
} catch {
    Pass-Job "invalid JSON response"
}

$summary = $data.summary
if ($summary) { Write-Host $summary }
Evaluate-Gate -Completed ([bool]$data.review_completed) -Score $data.score
